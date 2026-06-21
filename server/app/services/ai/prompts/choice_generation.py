def build_choice_refinement_prompt(context: str) -> str:
    return f"""Given the current story context, generate 2-3 meaningful choices for the player.

CONTEXT:
{context}

Each choice should:
- Feel natural in the current situation
- Lead to meaningfully different outcomes
- Reflect different player personalities (bold, cautious, curious, etc.)

Respond with JSON:
{{
  "choices": [
    {{ "text": "Choice text shown to player", "consequence": "Brief internal note about outcome" }}
  ]
}}"""
