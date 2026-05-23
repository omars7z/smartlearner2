import { useEffect, useState } from 'react'
import { Bot, SendHorizontal } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { useToast } from '../context/ToastContext'
import { useDashboard } from '../context/DashboardContext'
import { qaApi } from '../services/api'
import { getStudentIdForApi } from '../utils/studentIdentity'
import {
  clearQaMessages,
  getActiveUserId,
  getUserCurrentTrack,
  loadQaMessages,
  saveQaMessages,
} from '../utils/dashboardStorage'

interface ExplanationPayload {
  hook?: string
  core_explanation?: string
  example?: {
    type?: string
    content?: string
  }
  common_mistake?: string
  quick_check?: {
    question?: string
    hint?: string
    answer?: string
  }
  confidence_score?: number
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  routing?: string[]
  suggestions?: string[]
  explanation?: ExplanationPayload
  sources?: string[]
}

function extractTopicHint(input: string): string {
  const lower = input.toLowerCase()
  const m =
    lower.match(/\b(variable assignment|variables?|loops?|functions?|conditionals?|lists?|dictionaries?|tuples?|strings?|debugging|errors?)\b/) ||
    lower.match(/\b([a-z][a-z0-9_]{3,})\b/)
  return (m?.[1] || 'python basics').trim()
}

function extractQuickCheckQuestion(markdown: string): string | null {
  const text = (markdown || '').trim()
  if (!text) return null
  // Matches:
  // > 💡 **Quick check:** ....
  // or non-quoted "💡 Quick check: ..."
  const m1 = text.match(/^\s*>\s*💡\s*\*\*Quick check:\*\*\s*(.+)\s*$/im)
  if (m1?.[1]) return m1[1].trim()
  const m2 = text.match(/^\s*💡\s*Quick check:\s*(.+)\s*$/im)
  if (m2?.[1]) return m2[1].trim()
  return null
}

function overlapRatio(a: string, b: string): number {
  const ta = new Set(
    a
      .toLowerCase()
      .split(/[^a-zA-Z0-9_]+/)
      .filter((x) => x.length > 2),
  )
  const tb = new Set(
    b
      .toLowerCase()
      .split(/[^a-zA-Z0-9_]+/)
      .filter((x) => x.length > 2),
  )
  if (!ta.size || !tb.size) return 0
  let common = 0
  ta.forEach((t) => {
    if (tb.has(t)) common += 1
  })
  return common / Math.max(ta.size, 1)
}

function harderQuickCheck(question: string): string {
  const q = question.trim()
  return `Harder check: ${q} Then explain one edge case in one sentence.`
}

export default function DashboardQA() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const { addToast } = useToast()
  const { knowledgeMap, masteryLevel, mergeAnalyticsFromQA } = useDashboard()
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [qaTopic, setQaTopic] = useState<string>('python basics')
  const [qaMasteredLastCheck, setQaMasteredLastCheck] = useState(false)
  const [waitingForAnswer, setWaitingForAnswer] = useState(false)
  const [currentQuickCheck, setCurrentQuickCheck] = useState<ExplanationPayload['quick_check'] | null>(null)
  const selectedTrack = (() => {
    const t = getUserCurrentTrack()
    return t === 'deep_learning' ? 'deep_learning' : 'python'
  })()
  const sourceLabel = selectedTrack === 'deep_learning' ? 'Deep Learning' : 'Python for Everybody'

  // Load persisted chat on first mount
  useEffect(() => {
    const parsed = loadQaMessages<ChatMessage>(getActiveUserId())
    if (parsed.length > 0) {
      setMessages(parsed)
    }
  }, [])

  // Persist chat whenever it changes
  useEffect(() => {
    saveQaMessages(getActiveUserId(), messages)
  }, [messages])

  const handleAsk = async (override?: string) => {
    const raw = (override ?? question).trim()
    if (!raw || loading) return

    // If we are answering a Quick Check, evaluate locally and do NOT call the API
    if (waitingForAnswer && currentQuickCheck) {
      const studentAnswer = raw
      if (studentAnswer.toLowerCase().trim() === 'next') {
        setMessages((prev) => [
          ...prev,
          { role: 'user', content: studentAnswer },
          { role: 'assistant', content: 'Got it — moving on. Ask your next question.', routing: [] },
        ])
        setQuestion('')
        setWaitingForAnswer(false)
        setCurrentQuickCheck(null)
        setQaMasteredLastCheck(false)
        return
      }
      const correct = (currentQuickCheck.answer ?? '').toLowerCase().trim()
      const studentNorm = studentAnswer.toLowerCase().trim()
      const isGradable = !!correct
      const isCorrect = isGradable && (studentNorm.includes(correct) || correct.includes(studentNorm))
      const partialByOverlap =
        !isCorrect &&
        overlapRatio(studentNorm, correct || (currentQuickCheck.question ?? '')) >= 0.35
      const looksWrong = !isCorrect && !partialByOverlap

      if (isCorrect) {
        const followUp = harderQuickCheck(currentQuickCheck.question ?? 'Apply the same concept in code.')
        setMessages((prev) => [
          ...prev,
          { role: 'user', content: studentAnswer },
          {
            role: 'assistant',
            content:
              `✅ Exactly right! Your answer matches the target concept and applies it correctly.\n\n` +
              `💡 **Quick check:** ${followUp}\n` +
              `_Reply with your answer or type "next" to continue._`,
            routing: [],
          },
        ])
        setCurrentQuickCheck({
          question: followUp,
          hint: currentQuickCheck.hint ?? 'Focus on why your code works, not only what it prints.',
          answer: currentQuickCheck.answer ?? '',
        })
        setWaitingForAnswer(true)
        setQaMasteredLastCheck(true)
        setQuestion('')
        return
      }

      if (partialByOverlap) {
        const reAsk =
          `Can you answer again with one concrete line of code and one sentence why it works?\n` +
          `Original check: ${currentQuickCheck.question ?? 'Explain your reasoning.'}`
        setMessages((prev) => [
          ...prev,
          { role: 'user', content: studentAnswer },
          {
            role: 'assistant',
            content:
              `🟡 Almost! You are close, but you missed a precise detail.\n\n` +
              `💡 **Quick check:** ${reAsk}\n` +
              `_Reply with your answer or type "next" to continue._`,
            routing: [],
          },
        ])
        setCurrentQuickCheck({
          question: reAsk,
          hint: currentQuickCheck.hint ?? 'Be explicit about conversion/type handling.',
          answer: currentQuickCheck.answer ?? '',
        })
        setWaitingForAnswer(true)
        setQaMasteredLastCheck(false)
        setQuestion('')
        return
      }

      if (looksWrong) {
        const reExplain = currentQuickCheck.hint
          ? `Try this angle: ${currentQuickCheck.hint}`
          : 'Try this angle: treat values and their types separately before combining them.'
        const reAsk =
          `Re-answer this check using that idea: ${currentQuickCheck.question ?? 'What is the correct approach?'}`
        setMessages((prev) => [
          ...prev,
          { role: 'user', content: studentAnswer },
          {
            role: 'assistant',
            content:
              `❌ Not quite — ${reExplain}\n\n` +
              `💡 **Quick check:** ${reAsk}\n` +
              `_Reply with your answer or type "next" to continue._`,
            routing: [],
          },
        ])
        setCurrentQuickCheck({
          question: reAsk,
          hint: currentQuickCheck.hint ?? 'Use a simple concrete example.',
          answer: currentQuickCheck.answer ?? '',
        })
        setWaitingForAnswer(true)
        setQaMasteredLastCheck(false)
        setQuestion('')
        return
      }

      setQuestion('')
      setWaitingForAnswer(true)
      return
    }

    const q = raw
    setQaTopic(extractTopicHint(q))
    setMessages((prev) => [...prev, { role: 'user', content: q }])
    if (!override) setQuestion('')
    setLoading(true)
    try {
      const studentId = getStudentIdForApi()
      const studentContext: Record<string, unknown> = {
        student_id: studentId,
        mastery_level: masteryLevel,
        knowledge_map: knowledgeMap,
        track: selectedTrack,
        active_course: sourceLabel,
        qa_topic: qaTopic,
        qa_followup: messages.length >= 2,
        qa_confused: /i don't get|still confused|مش فاهم|مو فاهم|مش فاهمة|مو فاهمة|مش واضح/i.test(q),
        qa_mastered_last_check: qaMasteredLastCheck,
      }
      // Course-wide Q&A: do not scope by current_topic; backend uses RAG grounded to selected track.
      const data = await qaApi.ask(q, undefined, studentContext)
      const result = data.result ?? {}
      const rag = (result.rag ?? {}) as Record<string, unknown>

      // Collect explanation object (JSON) if available
      let explanationObj: ExplanationPayload | undefined
      let explanationText: string | null = null
      const rawExplanation = result.explanation
      if (rawExplanation && typeof rawExplanation === 'object') {
        explanationObj = rawExplanation as ExplanationPayload
        explanationText = explanationObj.core_explanation ?? ''
      } else if (typeof rawExplanation === 'string') {
        try {
          const parsed = JSON.parse(rawExplanation) as ExplanationPayload
          if (parsed && parsed.core_explanation) {
            explanationObj = parsed
            explanationText = parsed.core_explanation ?? rawExplanation
          } else {
            explanationText = rawExplanation
          }
        } catch {
          explanationText = rawExplanation
        }
      } else if (Array.isArray(rag.selected_chunks) && rag.selected_chunks.length) {
        explanationText = (rag.selected_chunks as { text?: string; content?: string }[])
          .map((c) => c.text || c.content)
          .filter(Boolean)
          .join('\n\n')
      }

      // Sources from RAG chunks
      const chunkSourcesRaw =
        (Array.isArray(rag.selected_chunks) ? rag.selected_chunks : []) as { source?: string }[]
      const chunksAlt = (Array.isArray(rag.chunks) ? rag.chunks : []) as { source?: string }[]
      const chunkSources = chunkSourcesRaw.length ? chunkSourcesRaw : chunksAlt
      const srcSet = new Set<string>()
      for (const c of chunkSources) {
        if (c?.source) srcSet.add(c.source)
      }
      const sources = Array.from(srcSet)

      const routing = (data.routing?.steps as string[]) ?? []
      const suggestions = (result.suggestions as string[]) ?? []
      const finalAnswer = (explanationText ?? '').trim() || 'No explanation returned. Try another question.'

      mergeAnalyticsFromQA(result.analytics)

      // Capture Quick Check for follow-up interaction (if provided)
      const quickFromObj = (explanationObj?.quick_check?.question ?? '').trim()
      const quickFromMarkdown = extractQuickCheckQuestion(finalAnswer)
      const quickQuestion = quickFromObj || quickFromMarkdown || ''
      if (quickQuestion) {
        setCurrentQuickCheck(
          explanationObj?.quick_check ?? {
            question: quickQuestion,
            hint: '',
            answer: '',
          },
        )
        setWaitingForAnswer(true)
      } else {
        setCurrentQuickCheck(null)
        setWaitingForAnswer(false)
      }
      // Reset one-shot mastery hint after it has been sent once.
      if (qaMasteredLastCheck) setQaMasteredLastCheck(false)

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: finalAnswer, routing, suggestions, explanation: explanationObj, sources },
      ])
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String((err as Error).message) : 'Request failed.'
      const status = err && typeof err === 'object' && 'response' in err && (err as { response?: { status?: number } }).response?.status
      addToast('error', status === 401 ? 'Please log in to use Q&A.' : 'API request failed. Is the backend running on port 8000?')
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${msg}. Check the backend and try again.`, routing: [] },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleSuggestionClick = (text: string) => {
    void handleAsk(text)
  }

  const handleClearChat = () => {
    setMessages([])
    clearQaMessages(getActiveUserId())
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div
        className="p-4 border-b flex items-center justify-between gap-3"
        style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div
            className="h-10 w-10 rounded-xl flex items-center justify-center animate-pulse shrink-0"
            style={{ background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }}
          >
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold text-[color:var(--text-primary)]">Ask AI Agents</h1>
            <p className="text-xs text-[color:var(--text-muted)] mt-1 max-w-xl">
              Answers are grounded in <span className="text-[color:var(--text-secondary)]">{sourceLabel}</span>{' '}
              via RAG for your selected track - ask anything covered there.
            </p>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {['MCP', 'RAG', 'Explain', 'Validate', 'Analytics'].map((label) => (
                <span key={label} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700/80 text-slate-300">
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={handleClearChat}
            className="text-[11px] px-2.5 py-1 rounded-full border border-[color:var(--border-color)] text-[color:var(--text-secondary)] hover:bg-white/5"
          >
            Clear chat
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-[color:var(--text-muted)] py-8 max-w-md mx-auto">
            Ask about concepts and examples from your selected track materials. Analytics still sync from your session when available.
          </p>
        )}
        {messages.map((m, idx) => (
          <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                m.role === 'user'
                  ? 'text-white'
                  : 'bg-[var(--bg-card)] border border-[var(--border-color)] text-[color:var(--text-primary)]'
              }`}
              style={
                m.role === 'user'
                  ? { background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }
                  : { maxWidth: 600, lineHeight: 1.6 }
              }
            >
              {m.role === 'assistant' && m.explanation ? (
                <div className="space-y-3 text-sm">
                  <div className="prose prose-invert prose-sm max-w-none leading-7">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        pre: ({ children }) => (
                          <pre
                            className="rounded-md px-3 py-2 text-xs overflow-x-auto"
                            style={{
                              backgroundColor: 'rgba(15,23,42,0.9)',
                              color: '#e5e7eb',
                              fontFamily:
                                'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                            }}
                          >
                            {children}
                          </pre>
                        ),
                        code: ({ className, children, ...props }) => {
                          const isInline = !className
                          if (isInline) {
                            return (
                              <code className="px-1 py-0.5 rounded bg-slate-700/70 text-slate-100" {...props}>
                                {children}
                              </code>
                            )
                          }
                          return (
                            <code className={className} {...props}>
                              {children}
                            </code>
                          )
                        },
                      }}
                    >
                      {m.content}
                    </ReactMarkdown>
                  </div>

                  {m.sources && m.sources.length > 0 && (
                    <p className="text-[11px] text-[color:var(--text-muted)] pt-1">
                      📚 Source: {m.sources.join(', ')}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-sm break-words whitespace-pre-wrap">{m.content}</p>
              )}

              {m.role === 'assistant' && m.routing && m.routing.length > 0 && (
                <p className="text-[10px] text-[color:var(--text-muted)] mt-2">
                  Pipeline: {m.routing.join(' → ')}
                </p>
              )}
              {m.role === 'assistant' && m.suggestions && m.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {m.suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => handleSuggestionClick(s)}
                      className="px-2.5 py-1 text-[11px] rounded-full border border-[color:var(--border-color)] text-[color:var(--text-secondary)] hover:bg-white/5"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-3 text-sm text-[color:var(--text-muted)]" style={{ backgroundColor: 'var(--bg-card)' }}>
              Thinking…
            </div>
          </div>
        )}
      </div>
      <div className="p-4 border-t" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}>
        <div className="flex gap-2 max-w-3xl mx-auto">
          {waitingForAnswer && currentQuickCheck?.question && (
            <div className="flex-1 mb-2 text-[11px] text-[color:var(--text-muted)]">
              📝 Answering Quick Check: {currentQuickCheck.question}
            </div>
          )}
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAsk()}
            placeholder={waitingForAnswer ? 'Type your answer…' : 'Ask the AI agents…'}
            className="flex-1 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2"
            style={{ backgroundColor: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          />
          <button
            type="button"
            onClick={() => void handleAsk()}
            disabled={loading || !question.trim()}
            className="rounded-xl px-4 py-3 text-white font-semibold flex items-center gap-2 disabled:opacity-60 shrink-0"
            style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
          >
            <SendHorizontal className="h-5 w-5" />
            {waitingForAnswer ? 'Check Answer' : 'Ask Agents'}
          </button>
        </div>
      </div>
    </div>
  )
}
