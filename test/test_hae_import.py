# test/test_hae_import.py
def test_hae_import(conn):
    """Verify HAE data imported correctly"""
    
    cur = conn.cursor()
    
    # Check Sep 22 partial day
    cur.execute("""
        SELECT intake_kcal, protein_g, carbs_g, fat_g 
        FROM daily_facts 
        WHERE fact_date = '2025-09-22'
    """)
    row = cur.fetchone()
    assert row[0] == 290  # calories
    assert row[1] == 44   # protein
    assert row[2] == 19   # carbs
    assert row[3] == 3    # fat
    
    # Check date range coverage
    cur.execute("""
        SELECT COUNT(DISTINCT date) 
        FROM hae_metrics_parsed 
        WHERE import_id = (SELECT MAX(import_id) FROM hae_raw)
    """)
    days = cur.fetchone()[0]
    assert days == 29  # Aug 25 - Sep 22
    
    print("✓ HAE import tests passed")
