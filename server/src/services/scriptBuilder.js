import { getDb } from '../db/database.js';

export const scriptBuilder = {
  /**
   * Convert the AI's structured openingScript into Monogatari script format.
   * Returns { 'Start': [...statements], 'choice_xxx_0': [...], ... }
   */
  buildInitialScript(storyData) {
    const script = {};
    const { statements: startStatements, extraLabels } = this._convertStatementArray(
      storyData.openingScript,
      'Start'
    );
    script['Start'] = startStatements;
    Object.assign(script, extraLabels);
    return script;
  },

  /**
   * Convert a runtime AI dialogue response into Monogatari statements.
   * Returns { labelName, statements, extraLabels }
   */
  buildRuntimeLabel(aiOutput, labelPrefix = 'dynamic') {
    const labelName = `${labelPrefix}_${Date.now()}`;
    const { statements, extraLabels } = this._convertStatementArray(
      aiOutput.statements,
      labelName
    );

    // Append choices
    if (aiOutput.choices && aiOutput.choices.length > 0) {
      const { choiceStatement, choiceLabels } = this._buildChoiceStatement(
        aiOutput.choices,
        labelName
      );
      statements.push(choiceStatement);
      Object.assign(extraLabels, choiceLabels);
    }

    return { labelName, statements, extraLabels };
  },

  _convertStatementArray(stmtArray, parentLabel) {
    const statements = [];
    const extraLabels = {};

    for (const stmt of stmtArray) {
      if (stmt.type === 'choice' || (stmt.choices && stmt.choices.length > 0)) {
        // This is a choice point within the script
        const choices = stmt.choices || [];
        const { choiceStatement, choiceLabels } = this._buildChoiceStatement(choices, parentLabel);
        statements.push(choiceStatement);
        Object.assign(extraLabels, choiceLabels);
      } else {
        const converted = this._convertSingle(stmt);
        if (converted) statements.push(converted);
      }
    }

    return { statements, extraLabels };
  },

  _convertSingle(stmt) {
    switch (stmt.type) {
      case 'narration':
        return stmt.text;

      case 'dialogue':
        return `${stmt.speaker}:${stmt.expression || 'neutral'} ${stmt.text}`;

      case 'scene_change':
        return `show scene ${stmt.sceneId} with fadeIn`;

      case 'show_character': {
        const expr = stmt.expression || 'neutral';
        const pos = stmt.position || 'center';
        return `show character ${stmt.characterId} ${expr} at ${pos} with fadeIn`;
      }

      case 'hide_character':
        return `hide character ${stmt.characterId} with fadeOut`;

      default:
        return null;
    }
  },

  _buildChoiceStatement(choices, parentLabel) {
    const choiceObj = { Choice: {} };
    const choiceLabels = {};

    choices.forEach((choice, i) => {
      const labelName = `${parentLabel}_choice_${i}`;
      choiceObj.Choice[labelName] = {
        Text: choice.text,
        Do: `jump ${labelName}`,
        _consequence: choice.consequence,
      };
      // Create a placeholder label for each choice — will be populated by the
      // gameplay controller when the player selects it
      choiceLabels[labelName] = [
        `Waiting for AI to continue the story...`,
      ];
    });

    return { choiceStatement: choiceObj, choiceLabels };
  },

  /**
   * Save a script label to the database.
   */
  saveLabel(sessionId, labelName, statements) {
    const db = getDb();
    db.prepare(`
      INSERT OR REPLACE INTO script_labels (session_id, label_name, statements)
      VALUES (?, ?, ?)
    `).run(sessionId, labelName, JSON.stringify(statements));
  },

  /**
   * Load all script labels for a session from the database.
   * Returns a Monogatari-compatible script object.
   */
  loadScript(sessionId) {
    const db = getDb();
    const rows = db
      .prepare('SELECT label_name, statements FROM script_labels WHERE session_id = ? ORDER BY sort_order')
      .all(sessionId);

    const script = {};
    for (const row of rows) {
      script[row.label_name] = JSON.parse(row.statements);
    }
    return script;
  },
};
