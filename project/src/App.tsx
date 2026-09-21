import AnimatedBackground from '@/components/AnimatedBackground';
import Navbar from '@/components/Navbar';
import Hero from '@/components/Hero';
import HowItWorks from '@/components/HowItWorks';
import ShowDontTell from '@/components/ShowDontTell';
import Features from '@/components/Features';
import DashboardMockup from '@/components/DashboardMockup';
import RadarScout from '@/components/RadarScout';
import CTA from '@/components/CTA';
import FAQ, { Footer } from '@/components/FAQ';
import Dashboard from '@/components/Dashboard';
import { useAuth } from '@/context/AuthContext';

function App() {
  const { session, loading } = useAuth();

  // Avoid a flash of the landing page while we check for an existing session.
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-scout-400 border-t-transparent" />
      </div>
    );
  }

  // Signed in — swap the screen entirely to the Dashboard.
  if (session) {
    return <Dashboard />;
  }

  // Otherwise, render the landing page.
  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <AnimatedBackground />
      <Navbar />
      <main>
        <Hero />
        <HowItWorks />
        <ShowDontTell />
        <Features />
        <DashboardMockup />
        <RadarScout />
        <CTA />
        <FAQ />
      </main>
      <Footer />
    </div>
  );
}

export default App;