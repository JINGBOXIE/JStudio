# ============================================================
# SNAPSHOT DB (FULL VERSION - COMPATIBLE WITH premax_snapshot_run)
# ============================================================

import pymysql
import json


# ------------------------------------------------------------
# DB CONFIG
# ------------------------------------------------------------
class DBConfig:
    def __init__(self, host, user, password, database):
        self.host = host
        self.user = user
        self.password = password
        self.database = database


# ------------------------------------------------------------
# SNAPSHOT DB WRITER
# ------------------------------------------------------------
class SnapshotDBWriter:
    def __init__(self, db_cfg: DBConfig):
        self.conn = pymysql.connect(
            host=db_cfg.host,
            user=db_cfg.user,
            password=db_cfg.password,
            database=db_cfg.database,
            autocommit=True,
            charset="utf8mb4",
        )

    # ---------------------------------------------------------
    # LOAD (RESUME)
    # ---------------------------------------------------------
    def load_run_for_resume(self, run_id):
        sql = """
        SELECT master_seed, shoes_done, shoes_target, params_json
        FROM premax_snapshot_run
        WHERE run_id = %s
        """

        with self.conn.cursor() as cur:
            cur.execute(sql, (run_id,))
            row = cur.fetchone()

        if not row:
            raise Exception(f"[ERROR] Run ID not found: {run_id}")

        master_seed, shoes_done, shoes_target, params_json = row

        # JSON 解析
        try:
            params = json.loads(params_json)
        except Exception:
            params = {}

        return master_seed, shoes_done, shoes_target, params

    # ---------------------------------------------------------
    # UPSERT (CHECKPOINT)
    # ---------------------------------------------------------
    def upsert_run_checkpoint(
        self,
        run_id,
        mode,
        master_seed,
        params,
        shoes_target,
        shoes_done,
        snapshots_done,
        states_touched,
        finished,
    ):
        sql = """
        INSERT INTO premax_snapshot_run (
            run_id, mode, master_seed, params_json,
            shoes_target, shoes_done,
            snapshots_done, states_touched,
            started_at, updated_at, finished_at
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            NOW(), NOW(), NULL
        )
        ON DUPLICATE KEY UPDATE
            shoes_done = VALUES(shoes_done),
            snapshots_done = VALUES(snapshots_done),
            states_touched = VALUES(states_touched),
            updated_at = NOW(),
            finished_at = CASE WHEN %s = 1 THEN NOW() ELSE NULL END
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id,
                    mode,
                    master_seed,
                    json.dumps(params),
                    shoes_target,
                    shoes_done,
                    snapshots_done,
                    states_touched,
                    int(finished),
                ),
            )

    # ---------------------------------------------------------
    # CREATE RUN (OPTIONAL INIT)
    # ---------------------------------------------------------
    def create_run_if_not_exists(
        self,
        run_id,
        mode,
        master_seed,
        params,
        shoes_target,
    ):
        sql = """
        INSERT IGNORE INTO premax_snapshot_run (
            run_id, mode, master_seed, params_json,
            shoes_target, shoes_done,
            snapshots_done, states_touched,
            started_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s,
            %s, 0,
            0, 0,
            NOW(), NOW()
        )
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id,
                    mode,
                    master_seed,
                    json.dumps(params),
                    shoes_target,
                ),
            )

    # ---------------------------------------------------------
    # MARK FINISHED
    # ---------------------------------------------------------
    def mark_finished(self, run_id):
        sql = """
        UPDATE premax_snapshot_run
        SET finished_at = NOW(),
            updated_at = NOW()
        WHERE run_id = %s
        """

        with self.conn.cursor() as cur:
            cur.execute(sql, (run_id,))

    # ---------------------------------------------------------
    # SAFE LOAD (NO CRASH VERSION)
    # ---------------------------------------------------------
    def try_load_run(self, run_id):
        """
        不抛异常版本，用于自动 fallback
        """
        try:
            return self.load_run_for_resume(run_id)
        except Exception:
            return None, 0, None, {}

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------
    def close(self):
        if self.conn:
            self.conn.close()
