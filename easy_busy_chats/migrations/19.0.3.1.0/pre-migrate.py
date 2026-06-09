def migrate(cr, version):
    # Remove duplicate records that would violate the unique(provider, chat_id, contact_id)
    # constraint once provider is lowercased — keep the row with the smallest id.
    cr.execute("""
        DELETE FROM easy_busy_chat_link
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM easy_busy_chat_link
            GROUP BY LOWER(provider), chat_id, contact_id
        )
    """)
    cr.execute("""
        UPDATE easy_busy_chat_link
        SET provider = LOWER(provider)
        WHERE provider != LOWER(provider)
    """)
