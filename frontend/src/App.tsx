import { Routes, Route, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import { DashboardProvider } from './context/DashboardContext'
import DashboardLayout from './components/DashboardLayout'
import DashboardHome from './pages/DashboardHome'
import DashboardPlacement from './pages/DashboardPlacement'
import DashboardSyllabus from './pages/DashboardSyllabus'
import DashboardLessons from './pages/DashboardLessons'
import DashboardExams from './pages/DashboardExams'
import DashboardAnalytics from './pages/DashboardAnalytics'
import DashboardQA from './pages/DashboardQA'
import DashboardSettings from './pages/DashboardSettings'
import DashboardResources from './pages/DashboardResources'
import { ToastContainer } from './components/ToastContainer'

function isAdminUser(): boolean {
  try {
    const raw = localStorage.getItem('smartlearner-current-user')
    if (!raw) return false
    const u = JSON.parse(raw)
    return u?.role === 'admin'
  } catch (_) {
    return false
  }
}

function App() {
  return (
    <>
      <AnimatePresence mode="wait">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/dashboard"
            element={
              <DashboardProvider>
                <DashboardLayout />
              </DashboardProvider>
            }
          >
            <Route index element={<DashboardHome />} />
            <Route path="placement" element={<DashboardPlacement />} />
            <Route path="syllabus" element={<DashboardSyllabus />} />
            <Route path="lessons" element={<DashboardLessons />} />
            <Route path="exams" element={<DashboardExams />} />
            <Route
              path="resources"
              element={isAdminUser() ? <DashboardResources /> : <Navigate to="/dashboard" replace />}
            />
            <Route path="analytics" element={<DashboardAnalytics />} />
            <Route path="qa" element={<DashboardQA />} />
            <Route path="settings" element={<DashboardSettings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AnimatePresence>
      <ToastContainer />
    </>
  )
}

export default App
