"""
sample_paper_v2.csv 데이터를 MariaDB paper.sid_v_10 테이블에 적재하는 스크립트
(v1 대비 변경: author_orgname 컬럼 추가)
"""

import os
import pandas as pd
import mariadb
import sys
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("MARIADB_HOST", "localhost"),
    "port": int(os.getenv("MARIADB_PORT", "3306")),
    "user": os.getenv("MARIADB_USER"),
    "password": os.getenv("MARIADB_PASSWORD"),
}
DATABASE = os.getenv("MARIADB_DATABASE", "paper")
TABLE = "sid_v_10"

CSV_PATH = "data/sample_paper_v2.csv"


def create_database_and_table(cursor):
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` "
                   f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute(f"USE `{DATABASE}`")
    cursor.execute(f"DROP TABLE IF EXISTS `{TABLE}`")
    cursor.execute(f"""
        CREATE TABLE `{TABLE}` (
            mariadb_id       BIGINT,
            filename         VARCHAR(512),
            doi              VARCHAR(256),
            coverdate        BIGINT,
            title            TEXT,
            paper_keyword    TEXT,
            paper_text       TEXT,
            volume           SMALLINT,
            issue            SMALLINT,
            totalpage        SMALLINT,
            referencetotal   SMALLINT,
            author           TEXT,
            `references`     TEXT,
            chunk_id         SMALLINT,
            chunk_total_counts SMALLINT,
            bm25_keywords    TEXT,
            parser_ver       VARCHAR(20),
            author_orgname   TEXT,
            INDEX idx_filename (filename),
            INDEX idx_doi (doi),
            INDEX idx_coverdate (coverdate),
            INDEX idx_paper_keyword (paper_keyword(255)),
            INDEX idx_paper_text (paper_text(255))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    print(f"테이블 {DATABASE}.{TABLE} 생성 완료")


def insert_data(cursor, df):
    cols = list(df.columns)
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join([f"`{c}`" for c in cols])
    sql = f"INSERT INTO `{TABLE}` ({col_names}) VALUES ({placeholders})"

    count = 0
    for _, row in df.iterrows():
        values = []
        for c in cols:
            v = row[c]
            if pd.isna(v):
                values.append(None)
            elif c in ("mariadb_id", "coverdate"):
                values.append(int(v))
            elif c in ("volume", "issue", "totalpage", "referencetotal", "chunk_id", "chunk_total_counts"):
                values.append(int(v) if not pd.isna(v) else None)
            else:
                values.append(str(v))
        cursor.execute(sql, tuple(values))
        count += 1

    print(f"{count}건 INSERT 완료")


def main():
    # CSV 읽기
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    print(f"CSV 로드: {len(df)}행, 컬럼: {list(df.columns)}")

    # MariaDB 접속
    try:
        conn = mariadb.connect(**DB_CONFIG)
    except mariadb.Error as e:
        print(f"MariaDB 접속 실패: {e}")
        sys.exit(1)

    conn.auto_reconnect = True
    cursor = conn.cursor()

    try:
        create_database_and_table(cursor)
        insert_data(cursor, df)
        conn.commit()

        # 검증
        cursor.execute(f"SELECT COUNT(*) FROM `{TABLE}`")
        row_count = cursor.fetchone()[0]
        print(f"검증: 테이블 내 총 {row_count}건")
    except Exception as e:
        conn.rollback()
        print(f"에러 발생: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
