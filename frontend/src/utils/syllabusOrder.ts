import type { LessonDto, ModuleDto } from '../services/api'

/** Stable numeric order from API `order` or fallback from `lesson_N` id. */
export function lessonOrderKey(lesson: Pick<LessonDto, 'order' | 'lesson_id'>): number {
  if (typeof lesson.order === 'number' && !Number.isNaN(lesson.order)) {
    return lesson.order
  }
  const m = String(lesson.lesson_id || '').match(/^lesson_(\d+)$/)
  if (m) return Number(m[1])
  return 999_999
}

/**
 * Sort modules by the earliest root-lesson order in each module, then sort
 * root lessons and nested sub-lessons by `order_index` / `lesson_id` fallback.
 */
export function normalizeSyllabusModules(modules: ModuleDto[]): ModuleDto[] {
  const sortSubLessons = (subs: LessonDto[] | undefined) => {
    if (!subs?.length) return subs
    return [...subs].sort((a, b) => lessonOrderKey(a) - lessonOrderKey(b))
  }

  const withSortedLessons = modules.map((mod) => ({
    ...mod,
    lessons: [...(mod.lessons ?? [])]
      .sort((a, b) => lessonOrderKey(a) - lessonOrderKey(b))
      .map((l) => ({
        ...l,
        sub_lessons: sortSubLessons(l.sub_lessons),
      })),
  }))

  const moduleMinOrder = (mod: ModuleDto) => {
    const roots = mod.lessons ?? []
    if (!roots.length) return 999_999
    return Math.min(...roots.map((l) => lessonOrderKey(l)))
  }

  return [...withSortedLessons].sort((a, b) => moduleMinOrder(a) - moduleMinOrder(b))
}

/** Global course order: every root then its sub-lessons, sorted by `order`. */
export function flattenLessonsInCourseOrder(modules: ModuleDto[]): { lesson: LessonDto; module: ModuleDto }[] {
  const normalized = normalizeSyllabusModules(modules)
  const out: { lesson: LessonDto; module: ModuleDto }[] = []
  for (const mod of normalized) {
    for (const l of mod.lessons ?? []) {
      out.push({ lesson: l, module: mod })
      for (const s of l.sub_lessons ?? []) {
        out.push({ lesson: s, module: mod })
      }
    }
  }
  return out.sort((a, b) => lessonOrderKey(a.lesson) - lessonOrderKey(b.lesson))
}
