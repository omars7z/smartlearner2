import { motion } from 'framer-motion'
import { Cpu } from 'lucide-react'

const agentPositions = [
  { angle: 0, color: '#3B82F6' },
  { angle: 40, color: '#06B6D4' },
  { angle: 80, color: '#8B5CF6' },
  { angle: 120, color: '#10B981' },
  { angle: 160, color: '#F59E0B' },
  { angle: 200, color: '#EC4899' },
  { angle: 240, color: '#6366F1' },
  { angle: 280, color: '#14B8A6' },
  { angle: 320, color: '#F97316' },
]

export default function MCPDiagram() {
  const radius = 140
  const cx = 170
  const cy = 170

  return (
    <div className="relative w-[340px] h-[340px] mx-auto my-8">
      <svg className="w-full h-full" viewBox="0 0 340 340">
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {agentPositions.map((pos, i) => {
          const x = cx + radius * Math.cos((pos.angle * Math.PI) / 180)
          const y = cy + radius * Math.sin((pos.angle * Math.PI) / 180)
          return (
            <motion.line
              key={i}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke={pos.color}
              strokeWidth="2"
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.6 }}
              transition={{ duration: 0.8, delay: i * 0.05 }}
            />
          )
        })}
        {agentPositions.map((pos, i) => {
          const x = cx + radius * Math.cos((pos.angle * Math.PI) / 180)
          const y = cy + radius * Math.sin((pos.angle * Math.PI) / 180)
          return (
            <motion.circle
              key={`node-${i}`}
              cx={x}
              cy={y}
              r="8"
              fill={pos.color}
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.9 }}
              transition={{ delay: 0.5 + i * 0.05, duration: 0.5 }}
            />
          )
        })}
      </svg>
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.3, type: 'spring', stiffness: 200 }}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-[#3B82F6] to-[#06B6D4] shadow-lg shadow-blue-500/50"
      >
        <Cpu className="h-10 w-10 text-white" />
      </motion.div>
    </div>
  )
}
