import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import './Login.css';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();

  const backgroundRef = useRef(null);
  const rafRef = useRef(null);
  const targetRef = useRef({ x: 0, y: 0 });
  const currentRef = useRef({ x: 0, y: 0 });

  // Subtle parallax: the orb layer drifts a little toward the cursor.
  useEffect(() => {
    const handleMouseMove = (e) => {
      const { innerWidth, innerHeight } = window;
      targetRef.current = {
        x: (e.clientX / innerWidth - 0.5) * 2,
        y: (e.clientY / innerHeight - 0.5) * 2,
      };
    };

    const tick = () => {
      const el = backgroundRef.current;
      if (el) {
        const cur = currentRef.current;
        const tgt = targetRef.current;
        // Ease toward the target for a smooth, floaty feel.
        cur.x += (tgt.x - cur.x) * 0.05;
        cur.y += (tgt.y - cur.y) * 0.05;
        el.style.setProperty('--parallax-x', `${cur.x * 18}px`);
        el.style.setProperty('--parallax-y', `${cur.y * 18}px`);
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    window.addEventListener('mousemove', handleMouseMove);
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // A handful of twinkling stars scattered around the scene.
  const stars = useMemo(() => {
    return Array.from({ length: 24 }).map((_, i) => ({
      id: i,
      top: `${Math.random() * 100}%`,
      left: `${Math.random() * 100}%`,
      size: `${1 + Math.random() * 2}px`,
      delay: `${Math.random() * 6}s`,
      duration: `${3 + Math.random() * 4}s`,
    }));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      return;
    }
    setIsLoading(true);
    await login(username, password);
    setIsLoading(false);
  };

  return (
    <div className="login-container">
      <div className="login-background" ref={backgroundRef}>
        <div className="star-field">
          {stars.map((star) => (
            <span
              key={star.id}
              className="star"
              style={{
                top: star.top,
                left: star.left,
                width: star.size,
                height: star.size,
                animationDelay: star.delay,
                animationDuration: star.duration,
              }}
            />
          ))}
        </div>
        <div className="orb-layer">
          <div className="orb-wrapper orb-1-wrapper">
            <div className="login-orb orb-1"></div>
          </div>
          <div className="orb-wrapper orb-2-wrapper">
            <div className="login-orb orb-2"></div>
          </div>
          <div className="orb-wrapper orb-3-wrapper">
            <div className="login-orb orb-3"></div>
          </div>
        </div>
      </div>
      
      <div className="login-card">
        <div className="login-brand">
          <div className="login-icon">⚡</div>
          <h1>NEBULA</h1>
          <p>Cloud Code Runner</p>
        </div>
        
        <form onSubmit={handleSubmit} className="login-form">
          <div className="input-group">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              autoComplete="username"
              disabled={isLoading}
              required
            />
          </div>
          <div className="input-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete="current-password"
              disabled={isLoading}
              required
            />
          </div>
          
          <button 
            type="submit" 
            className="btn btn-primary btn-block"
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <span className="spinner"></span>
                Logging in...
              </>
            ) : (
              <>
                <span>🚀</span> Launch
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;