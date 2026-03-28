import { motion } from 'framer-motion'
import Navbar from '../components/Navbar'
import Hero from '../components/Hero'
import Features from '../components/Features'
import Agents from '../components/Agents'
import HowItWorks from '../components/HowItWorks'
import Stats from '../components/Stats'
import About from '../components/About'
import Team from '../components/Team'
import Footer from '../components/Footer'

export default function Landing() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="min-h-screen bg-white dark:bg-slate-900"
    >
      <Navbar />
      <main>
        <Hero />
        <Features />
        <Agents />
        <HowItWorks />
        <Stats />
        <About />
        <Team />
        <Footer />
      </main>
    </motion.div>
  )
}
