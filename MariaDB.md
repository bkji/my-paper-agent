# MariaDB localPC setup해놓은것
접속 주소: localhost
port: 3306
id: root
password: Password19

database: paper
Character Set: utf8mb4
collate : utf8mb4_unicode_ci

## table생성
- 생성할 table명과 스키마는 다음과 같이 생성요청
database이름: paper
table이름: sid_v_09_01
``` table 스키마
column명	type	크기	index여부
---
mariadb_id	Int64		
filename	VarChar	512	index
doi	VarChar	256	index
coverdate	Int64		index
title	VarChar	65535	
paper_keyword	VarChar	65535	index
paper_text	VarChar	65535	index
volume	Int16		
issue	Int16		
totalpage	Int16		
referencetotal	Int16		
author	VarChar	65535	
references	VarChar	65535	
chunk_id	Int16		
chunk_total_counts	Int16		
bm25_keywords	VarChar	65535	
parser_ver	VarChar	20	
```
- table생성은 csv파일을 바탕으로 insert 수행