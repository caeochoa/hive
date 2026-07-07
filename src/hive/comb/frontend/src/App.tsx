import { Routes, Route } from 'react-router-dom'
import WorkerList from './pages/WorkerList'
import WorkerDashboard from './pages/WorkerDashboard'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WorkerList />} />
      <Route path="/workers/:name" element={<WorkerDashboard />} />
    </Routes>
  )
}
