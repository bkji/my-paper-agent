"""
Q&A 데이터셋 관리용 MariaDB 테이블 생성 스크립트
- qa_dataset: 1,080건 Q&A 데이터 저장
- date_parse_testcases: 날짜 파싱 테스트 케이스
"""

import os
import sys
import mariadb
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("MARIADB_HOST", "localhost"),
    "port": int(os.getenv("MARIADB_PORT", "3306")),
    "user": os.getenv("MARIADB_USER"),
    "password": os.getenv("MARIADB_PASSWORD"),
}
DATABASE = os.getenv("MARIADB_DATABASE", "paper")


def create_tables(cursor):
    cursor.execute(f"USE `{DATABASE}`")

    # qa_dataset 테이블
    cursor.execute("DROP TABLE IF EXISTS `date_parse_testcases`")
    cursor.execute("DROP TABLE IF EXISTS `qa_dataset`")

    cursor.execute("""
        CREATE TABLE `qa_dataset` (
            qa_id            INT AUTO_INCREMENT PRIMARY KEY,

            -- 분류 차원
            user_role        VARCHAR(20)   NOT NULL COMMENT 'R1~R8',
            user_role_name   VARCHAR(50)   NOT NULL COMMENT '한글 역할명',
            agent_type       VARCHAR(30)   NOT NULL COMMENT '13개 agent 중 하나',
            complexity       VARCHAR(10)   NOT NULL COMMENT 'C1/C2/C3',
            date_type        VARCHAR(10)   NOT NULL COMMENT 'D0/D1/D2/D3/D4',

            -- Q&A 본문
            query_text       TEXT          NOT NULL COMMENT '사용자 질문 원문 (Korean)',
            expected_answer  TEXT          NOT NULL COMMENT '기대 답변 구조 설명',
            answer_format    VARCHAR(30)   DEFAULT 'text' COMMENT 'text/table/structured/report',

            -- 날짜 파싱 메타데이터
            date_expression  VARCHAR(100)  DEFAULT NULL COMMENT '질문 내 날짜 표현 원문',
            parsed_from      INT           DEFAULT NULL COMMENT 'coverdate_from (YYYYMMDD)',
            parsed_to        INT           DEFAULT NULL COMMENT 'coverdate_to (YYYYMMDD)',
            reference_date   INT           DEFAULT NULL COMMENT '상대날짜 해석 기준일 (YYYYMMDD)',

            -- 검색/필터 메타데이터
            expected_filters JSON          DEFAULT NULL COMMENT '기대되는 필터 조건 JSON',
            expected_keywords VARCHAR(500) DEFAULT NULL COMMENT '핵심 검색 키워드',

            -- 도메인 메타데이터
            domain_category  VARCHAR(50)   DEFAULT NULL COMMENT 'OLED/MicroLED/QD/LCD/TFT/봉지/공통',
            sub_domain       VARCHAR(100)  DEFAULT NULL COMMENT '세부 기술 분류',

            -- 품질 관리
            difficulty_score TINYINT       DEFAULT 1 COMMENT '1~5 난이도',
            is_validated     TINYINT       DEFAULT 0 COMMENT '검증 완료 여부',
            created_at       DATETIME      DEFAULT CURRENT_TIMESTAMP,
            updated_at       DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            notes            TEXT          DEFAULT NULL COMMENT '비고',

            INDEX idx_user_role (user_role),
            INDEX idx_agent_type (agent_type),
            INDEX idx_complexity (complexity),
            INDEX idx_date_type (date_type),
            INDEX idx_domain (domain_category),
            INDEX idx_validated (is_validated),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    print("테이블 qa_dataset 생성 완료")

    # date_parse_testcases 테이블
    cursor.execute("""
        CREATE TABLE `date_parse_testcases` (
            test_id          INT AUTO_INCREMENT PRIMARY KEY,
            qa_id            INT           NOT NULL COMMENT 'FK to qa_dataset',
            input_expression VARCHAR(200)  NOT NULL COMMENT '원본 날짜 표현',
            date_type        VARCHAR(10)   NOT NULL COMMENT 'D1/D2/D3/D4',
            reference_date   INT           NOT NULL COMMENT '기준일 YYYYMMDD',
            expected_from    INT           NOT NULL COMMENT '기대 coverdate_from',
            expected_to      INT           NOT NULL COMMENT '기대 coverdate_to',
            locale           VARCHAR(10)   DEFAULT 'ko' COMMENT 'ko/en',

            INDEX idx_qa_id (qa_id),
            INDEX idx_date_type (date_type),
            FOREIGN KEY (qa_id) REFERENCES qa_dataset(qa_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    print("테이블 date_parse_testcases 생성 완료")


def main():
    try:
        conn = mariadb.connect(**DB_CONFIG, database=DATABASE)
    except mariadb.Error as e:
        print(f"MariaDB 접속 실패: {e}")
        sys.exit(1)

    cursor = conn.cursor()
    try:
        create_tables(cursor)
        conn.commit()

        # 검증
        cursor.execute("SHOW TABLES LIKE 'qa_%'")
        tables = cursor.fetchall()
        cursor.execute("SHOW TABLES LIKE 'date_parse%'")
        tables += cursor.fetchall()
        print(f"검증: 생성된 테이블 = {[t[0] for t in tables]}")
    except Exception as e:
        conn.rollback()
        print(f"에러: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
