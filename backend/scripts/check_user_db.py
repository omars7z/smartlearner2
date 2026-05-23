"""Quick DB sanity check for latest user(s)."""
import asyncio
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import engine


async def main() -> None:
    async with engine.connect() as conn:
        users = (await conn.execute(text(
            "SELECT id, email, full_name, created_at FROM users ORDER BY id DESC LIMIT 5"
        ))).mappings().all()
        print("=== RECENT USERS ===")
        for u in users:
            print(dict(u))

        if not users:
            return

        # Prefer MANOOSH if present
        uid = users[0]["id"]
        for u in users:
            name = (u.get("full_name") or "").upper()
            if "MANOOSH" in name or "manoosh" in (u.get("email") or "").lower():
                uid = u["id"]
                break

        label = next(u for u in users if u["id"] == uid)
        print(f"\n=== DETAIL user_id={uid} ({label.get('full_name') or label['email']}) ===")

        placements = (await conn.execute(
            text("""
                SELECT id, score, created_at,
                       questions_json->'placement_result'->>'level' AS level,
                       questions_json->'placement_result'->>'percentage' AS pct,
                       questions_json->'placement_result'->'strong_topics' AS strong,
                       questions_json->'placement_result'->'weak_topics' AS weak
                FROM placement_tests
                WHERE user_id = :uid
                ORDER BY created_at DESC LIMIT 3
            """),
            {"uid": uid},
        )).mappings().all()
        print("\n--- PLACEMENT ---")
        for p in placements:
            print(dict(p))

        courses = (await conn.execute(
            text("""
                SELECT c.id, c.title, c.level, c.created_at,
                       (SELECT COUNT(*) FROM lessons l WHERE l.course_id = c.id) AS lesson_count,
                       (SELECT COUNT(*) FROM lessons l WHERE l.course_id = c.id AND l.markdown_content IS NOT NULL AND l.markdown_content != '') AS generated
                FROM courses c
                WHERE c.user_id = :uid
                ORDER BY c.created_at DESC
            """),
            {"uid": uid},
        )).mappings().all()
        print("\n--- COURSES ---")
        for c in courses:
            print(dict(c))

        progress = (await conn.execute(
            text("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN passed THEN 1 ELSE 0 END) AS passed,
                       SUM(CASE WHEN attempts > 0 THEN 1 ELSE 0 END) AS attempted,
                       MAX(last_score) AS max_score
                FROM lesson_progress WHERE user_id = :uid
            """),
            {"uid": uid},
        )).mappings().first()
        print("\n--- LESSON PROGRESS ---")
        print(dict(progress))

        agents = (await conn.execute(
            text("""
                SELECT agent_name, stage, is_valid, created_at
                FROM agent_runs WHERE user_id = :uid
                ORDER BY created_at DESC LIMIT 25
            """),
            {"uid": uid},
        )).mappings().all()
        print("\n--- AGENT RUNS (latest 25) ---")
        for a in agents:
            print(dict(a))

        agent_summary = (await conn.execute(
            text("""
                SELECT agent_name, COUNT(*) AS cnt
                FROM agent_runs WHERE user_id = :uid
                GROUP BY agent_name ORDER BY cnt DESC
            """),
            {"uid": uid},
        )).mappings().all()
        print("\n--- AGENT COUNTS ---")
        for a in agent_summary:
            print(dict(a))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
