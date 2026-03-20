# Milvus

## Milvus database 및 collection 생성
mariaDB의 database이름: *paper*, table이름: *sid_v_09_01* 정보를 담기 위하여 
milvus의 database도 *m_paper*, collection은 *m_sid_v_09_01*로 생성

### collection시 필수 수행 사항
- paper_text를 주어진 embedding API를 사용하여 넣고 semantic search수행함
	- 생성되는 field name은 *embeddings*로 하고, src text는 *paper_text* 임.
	- 임베딩: bge-m3 사용하므로 1024 dimention을 가짐
	- 인덱스는 *IVF_FLAT*, metric은 *IP*, *nlist*는 128로 세팅	
- keywords 검색을 위하여 BM25사용
	- 생성되는 field name은 *bm25_keywords_sparse*로 만들고, src는 bm25_keywords임
	- function_type은 *pymilvus.FunctionType.BM25*사용
	- 인덱스는 *SPARSE_INVERTED_INDEX*, metrics은 *BM25*, *DAAT_MAXSCORE*를 사용한다.
- 임베딩모델의 이름을 남기기 위하여 신규 field인 *embedding_model_id*에 기록하여 *paper_text*가 *embeddings*으로 변환시 어떤 모델을 사용했는지 명시적으로 적어, 추후 분석에 이용할수 있도록 한다.

- 결과적으로 mariaDB의 내용은 그대로 유지하고, 3개의 신규 field를 생성하여 데이터를 넣는다.
