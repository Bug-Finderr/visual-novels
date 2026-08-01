import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="page page--narrow" style={{ textAlign: 'center', paddingTop: '4rem' }}>
      <div className="sfx" style={{ fontSize: '4.5rem' }}>404!</div>
      <h1 className="display" style={{ marginTop: '1rem' }}>This page went off-panel</h1>
      <p className="muted" style={{ marginBottom: '1.75rem' }}>
        The tale you're looking for isn't here.
      </p>
      <Link to="/" className="btn btn-primary btn-lg">Back to StoryPlex</Link>
    </div>
  );
}
