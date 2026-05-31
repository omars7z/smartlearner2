import type { LessonDto, ModuleDto } from '../services/api'

export interface LessonProgressEntry {
  passed: boolean
  accessible: boolean
  block_passed: boolean
  attempts: number
  last_score?: number | null
}

export interface LessonsProgressSummary {
  course_id: number
  completed_assessable: number
  total_assessable: number
  overall_percent: number
  lessons: Record<string, LessonProgressEntry>
}

export type LessonUiStatus = 'locked' | 'available' | 'completed' | 'failed'

/** Root overview hubs and non-final sub-parts have no quiz. */
export function isQuizCheckpoint(lesson: LessonDto): boolean {
  if (lesson.sub_lessons?.length) return false
  if (lesson.is_sub_lesson && lesson.is_final_sub_lesson === false) return false
  return true
}

export function resolveLessonUiStatus(
  lesson: LessonDto,
  progressMap: Record<string, LessonProgressEntry>,
): LessonUiStatus {
  const entry = progressMap[lesson.lesson_id]
  // Completed before locked — stale `accessible: false` must not override a passed block.
  if (entry?.block_passed) return 'completed'
  if (entry?.passed && isQuizCheckpoint(lesson)) return 'completed'
  if (entry && !entry.accessible) return 'locked'
  if (entry && entry.attempts > 0 && !entry.passed && isQuizCheckpoint(lesson)) return 'failed'
  return 'available'
}

/** After a passed quiz, unlock the next lesson in local state until progress API catches up. */
export function patchProgressAfterPass(
  map: Record<string, LessonProgressEntry>,
  passedLessonId: string,
  nextLessonId?: string | null,
): Record<string, LessonProgressEntry> {
  const next = { ...map }
  const prev = next[passedLessonId]
  next[passedLessonId] = {
    passed: true,
    accessible: true,
    block_passed: true,
    attempts: prev?.attempts ?? 1,
    last_score: prev?.last_score ?? 5,
  }
  if (nextLessonId) {
    const nxt = next[nextLessonId]
    next[nextLessonId] = {
      passed: nxt?.passed ?? false,
      accessible: true,
      block_passed: nxt?.block_passed ?? false,
      attempts: nxt?.attempts ?? 0,
      last_score: nxt?.last_score,
    }
  }
  return next
}

export function moduleProgressStats(
  mod: ModuleDto,
  progressMap: Record<string, LessonProgressEntry>,
): { done: number; total: number } {
  let done = 0
  let total = 0
  for (const les of mod.lessons ?? []) {
    if (les.sub_lessons?.length) {
      total += 1
      const final = les.sub_lessons[les.sub_lessons.length - 1]
      const st = resolveLessonUiStatus(final, progressMap)
      if (st === 'completed') done += 1
    } else {
      total += 1
      if (resolveLessonUiStatus(les, progressMap) === 'completed') done += 1
    }
  }
  return { done, total }
}

export function extractCourseIdFromModules(modules: ModuleDto[]): number | null {
  for (const mod of modules) {
    for (const les of mod.lessons ?? []) {
      if (typeof les.course_id === 'number') return les.course_id
      for (const sub of les.sub_lessons ?? []) {
        if (typeof sub.course_id === 'number') return sub.course_id
      }
    }
  }
  return null
}
