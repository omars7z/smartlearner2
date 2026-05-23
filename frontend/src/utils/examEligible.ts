import type { LessonDto, ModuleDto } from '../services/api'
import { flattenLessonsInCourseOrder } from './syllabusOrder'
import { isQuizCheckpoint, resolveLessonUiStatus, type LessonProgressEntry } from './lessonProgressUi'

export const COMPREHENSIVE_EXAM_LESSON_ID = 'track_comprehensive'

export interface ExamLessonOption {
  lesson_id: string
  label: string
  topic: string
  moduleTitle: string
}

export function buildCompletedExamLessonOptions(
  modules: ModuleDto[],
  progressMap: Record<string, LessonProgressEntry>,
): ExamLessonOption[] {
  const out: ExamLessonOption[] = []
  for (const { lesson, module } of flattenLessonsInCourseOrder(modules)) {
    if (lesson.sub_lessons?.length) {
      const final = lesson.sub_lessons[lesson.sub_lessons.length - 1]
      if (resolveLessonUiStatus(final, progressMap) === 'completed') {
        out.push({
          lesson_id: final.lesson_id,
          label: final.title || final.topic,
          topic: final.topic,
          moduleTitle: module.title,
        })
      }
      continue
    }
    if (resolveLessonUiStatus(lesson, progressMap) !== 'completed') continue
    if (!isQuizCheckpoint(lesson)) continue
    out.push({
      lesson_id: lesson.lesson_id,
      label: lesson.title || lesson.topic,
      topic: lesson.topic,
      moduleTitle: module.title,
    })
  }
  return out
}

export function isTrackReadyForComprehensiveExam(
  completedAssessable: number,
  totalAssessable: number,
): boolean {
  return totalAssessable > 0 && completedAssessable >= totalAssessable
}
