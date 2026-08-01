import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../lib/api.js';

const EPIGRAPHS = [
  'In the beginning was the word…',
  'A story is the shortest distance between two souls.',
  'Every world is born from a single thought.',
  'Patience — the ink is still drying.',
];

export default function Loading() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [progress, setProgress] = useState(0);
  const [text, setText] = useState('Connecting…');
  const [steps, setSteps] = useState([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const stepsRef = useRef(null);
  const epigraph = useRef(EPIGRAPHS[Math.floor(Math.random() * EPIGRAPHS.length)]).current;

  useEffect(() => {
    if (!id) { navigate('/'); return undefined; }
    const addStep = (t) =>
      setSteps((prev) => (prev.length && prev[prev.length - 1] === t ? prev : [...prev, t]));

    const source = api.sse(
      `/sessions/${id}/generate/status`,
      (data) => {
        setProgress(data.progress);
        setText(data.details);
        addStep(data.details);
        if (data.step === 'done') { setDone(true); source.close(); }
        if (data.step === 'error') { setError(data.details); source.close(); }
      },
      () => {
        api.get(`/sessions/${id}`).then((s) => {
          if (s.status === 'ready') { setProgress(100); setText('Generation complete.'); setDone(true); }
          else if (s.status === 'error') { setError('Generation failed. Try again.'); }
        }).catch(() => {});
      }
    );
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (stepsRef.current) stepsRef.current.scrollTop = stepsRef.current.scrollHeight;
  }, [steps]);

  return (
    <div className="page page--narrow">
      <div className="panel" style={{ textAlign: 'center' }}>
        <span className="eyebrow">Weaving</span>
        <h1 className="display" style={{ margin: '0.4rem 0 0.3rem' }}>Weaving your world</h1>
        <p className="muted" style={{ fontStyle: 'italic', marginBottom: '1.75rem' }}>“{epigraph}”</p>

        <div className="progress-track">
          <div className="progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <div className="progress-meta">
          <span className="progress-text">{text}</span>
          <span className="progress-pct">{progress}%</span>
        </div>

        {steps.length > 0 && (
          <div className="progress-steps" ref={stepsRef}>
            {steps.map((s, i) => (
              <div
                key={i}
                className={`step ${i === steps.length - 1 && !done && !error ? 'step-active' : 'step-done'}`}
              >
                {s}
              </div>
            ))}
          </div>
        )}

        {done && (
          <button className="btn btn-primary btn-lg btn-block" onClick={() => navigate(`/play/${id}`)}>
            <span className="btn-icon">▶</span> Begin the tale
          </button>
        )}
        {error && <div className="form-error">{error}</div>}
      </div>
    </div>
  );
}
