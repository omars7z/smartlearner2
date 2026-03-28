import { Link } from 'react-router-dom'
import { GraduationCap, Github, Linkedin, Mail } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

export default function Footer() {
  const { t } = useLanguage()

  return (
    <footer className="bg-[#0F172A] text-slate-300 py-16 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="grid md:grid-cols-4 gap-12">
          <div className="md:col-span-2">
            <Link to="/" className="flex items-center gap-2 mb-4">
              <GraduationCap className="h-8 w-8 text-[#3B82F6]" />
              <span className="bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] bg-clip-text text-xl font-bold text-transparent">
                SmartLearner
              </span>
            </Link>
            <p className="text-slate-400 max-w-md">{t.footer.tagline}</p>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">{t.footer.quickLinks}</h4>
            <ul className="space-y-2">
              <li>
                <a href="/#features" className="hover:text-[#06B6D4] transition-colors">
                  {t.nav.features}
                </a>
              </li>
              <li>
                <a href="/#agents" className="hover:text-[#06B6D4] transition-colors">
                  {t.nav.agents}
                </a>
              </li>
              <li>
                <a href="/#about" className="hover:text-[#06B6D4] transition-colors">
                  {t.nav.about}
                </a>
              </li>
              <li>
                <Link to="/login" className="hover:text-[#06B6D4] transition-colors">
                  {t.nav.login}
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Connect</h4>
            <div className="flex gap-4">
              <a
                href="#"
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                aria-label="GitHub"
              >
                <Github className="h-5 w-5" />
              </a>
              <a
                href="#"
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-[#0A66C2] transition-colors"
                aria-label="LinkedIn"
              >
                <Linkedin className="h-5 w-5" />
              </a>
              <a
                href="mailto:smartlearner@just.edu.jo"
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                aria-label="Email"
              >
                <Mail className="h-5 w-5" />
              </a>
            </div>
          </div>
        </div>
        <div className="mt-12 pt-8 border-t border-slate-700 text-center text-slate-500 text-sm">
          {t.footer.copyright}
        </div>
      </div>
    </footer>
  )
}
