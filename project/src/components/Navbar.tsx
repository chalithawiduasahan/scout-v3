import { useEffect, useState } from 'react';
import { Menu, X, LogOut } from 'lucide-react';
import { useScrollProgress } from '@/hooks/useScrollProgress';
import { useAuth } from '@/context/AuthContext';
import AuthModal from '@/components/AuthModal';

const links = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Proof engine', href: '#proof-engine' },
  { label: 'Dashboard', href: '#dashboard' },
  { label: 'FAQ', href: '#faq' },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'signup' | 'login' | null>(null);
  const progress = useScrollProgress();
  const { session, signOut } = useAuth();

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handler, { passive: true });
    return () => window.removeEventListener('scroll', handler);
  }, []);

  return (
    <>
      {authMode && <AuthModal initialMode={authMode} onClose={() => setAuthMode(null)} />}

      <nav
        className={`fixed top-0 left-0 right-0 z-40 transition-all duration-500 ${
          scrolled ? 'glass-strong py-3' : 'py-5'
        }`}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6">
          <a href="#" className="group flex items-center gap-2.5">
            <span className="font-display text-2xl font-bold tracking-tight text-white">
              Scout<span className="text-scout-400">.</span>
            </span>
          </a>

          <div className="hidden items-center gap-8 md:flex">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-sm font-medium text-ink-300 transition-colors hover:text-white"
              >
                {l.label}
              </a>
            ))}
          </div>

          <div className="hidden items-center gap-3 md:flex">
            {session ? (
              <>
                <span className="max-w-[180px] truncate text-sm text-ink-300">
                  {session.user.user_metadata?.full_name || session.user.email}
                </span>
                <button
                  onClick={() => signOut()}
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2.5 text-sm font-medium text-ink-200 transition-colors hover:text-white"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Log out
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setAuthMode('login')}
                  className="rounded-full px-4 py-2.5 text-sm font-semibold text-ink-200 transition-colors hover:text-white"
                >
                  Log in
                </button>
                <button
                  onClick={() => setAuthMode('signup')}
                  className="group relative inline-flex items-center gap-2 overflow-hidden rounded-full bg-gradient-to-r from-scout-400 to-aqua-500 px-5 py-2.5 text-sm font-semibold text-ink-950 transition-transform hover:scale-105"
                >
                  <span className="relative z-10">Sign up</span>
                </button>
              </>
            )}
          </div>

          <button
            onClick={() => setOpen(!open)}
            className="rounded-lg p-2 text-ink-200 md:hidden"
            aria-label="Toggle menu"
          >
            {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>

        {/* Scroll progress bar */}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-white/5">
          <div
            className="h-full bg-gradient-to-r from-scout-400 to-aqua-500 transition-all duration-75"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </nav>

      {/* Mobile menu */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-ink-950/80 backdrop-blur-md" onClick={() => setOpen(false)} />
          <div className="glass-strong absolute right-0 top-0 h-full w-72 p-6 pt-24">
            <div className="flex flex-col gap-4">
              {links.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="text-base font-medium text-ink-200 hover:text-white"
                >
                  {l.label}
                </a>
              ))}

              {session ? (
                <>
                  <span className="mt-2 truncate text-sm text-ink-400">
                    {session.user.user_metadata?.full_name || session.user.email}
                  </span>
                  <button
                    onClick={() => {
                      setOpen(false);
                      signOut();
                    }}
                    className="rounded-full border border-white/10 px-5 py-3 text-center text-sm font-semibold text-ink-200"
                  >
                    Log out
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => {
                      setOpen(false);
                      setAuthMode('login');
                    }}
                    className="mt-4 rounded-full border border-white/10 px-5 py-3 text-center text-sm font-semibold text-ink-200"
                  >
                    Log in
                  </button>
                  <button
                    onClick={() => {
                      setOpen(false);
                      setAuthMode('signup');
                    }}
                    className="rounded-full bg-gradient-to-r from-scout-400 to-aqua-500 px-5 py-3 text-center text-sm font-semibold text-ink-950"
                  >
                    Sign up
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}