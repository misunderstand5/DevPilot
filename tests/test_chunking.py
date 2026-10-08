from app.services.parsers import chunk_text

def test_chunk_text_nonempty():
    chunks=chunk_text('# H\n' + ('abcde'*300),max_chars=200,overlap_chars=20)
    assert len(chunks)>=2
    assert all(x['content'] for x in chunks)
