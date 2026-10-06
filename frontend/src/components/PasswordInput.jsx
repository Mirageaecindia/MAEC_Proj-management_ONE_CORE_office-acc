import { Eye, EyeOff } from 'lucide-react';
import { useState } from 'react';

/**
 * A password field with an eye button that shows or hides what was typed. Takes the
 * same props as an <input>; every password field in the app uses it.
 */
export function PasswordInput(props) {
  const [shown, setShown] = useState(false);
  return (
    <span className="password-input">
      <input {...props} type={shown ? 'text' : 'password'} />
      <button
        type="button"
        className="password-toggle"
        aria-label={shown ? 'Hide password' : 'Show password'}
        aria-pressed={shown}
        title={shown ? 'Hide password' : 'Show password'}
        onClick={() => setShown((value) => !value)}
      >
        {shown ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </span>
  );
}
