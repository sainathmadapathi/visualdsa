import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import { applyMotion, initialMotion } from './motion';
import './styles.css';
import './readability.css';
import './studio.css';
import './motion.css';
import './editorial.css';
import './loop.css';
import './home.css';
import './stage.css';
import './sheets.css';
import './structures.css';
import './poster.css';
applyMotion(initialMotion());  // Before the first paint, so nothing animates against the learner's choice.
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary full title="Visual DSA hit an unexpected problem." detail="Your drafts and notes are saved on this device. Reloading usually fixes it."><App /></ErrorBoundary></React.StrictMode>);
