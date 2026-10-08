SET @index_exists = (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'kb_document'
    AND index_name = 'idx_doc_source_uri'
);
SET @sql = IF(
  @index_exists = 0,
  'ALTER TABLE kb_document ADD INDEX idx_doc_source_uri(source_uri(191))',
  'SELECT 1'
);
PREPARE statement FROM @sql;
EXECUTE statement;
DEALLOCATE PREPARE statement;
