SELECT_USER_BY_USERNAME_SQL = """
    SELECT id, username, password_hash, role, fleet_id, is_active, deleted_at
    FROM app_user
    WHERE username = $1
      AND deleted_at IS NULL
"""

SELECT_USER_BY_ID_SQL = """
    SELECT id, username, password_hash, role, fleet_id, is_active, deleted_at
    FROM app_user
    WHERE id = $1
      AND deleted_at IS NULL
"""

INSERT_USER_SQL = """
    INSERT INTO app_user (username, password_hash, role, fleet_id)
    VALUES ($1, $2, $3, $4)
    RETURNING id
"""

UPDATE_USER_SQL = """
    UPDATE app_user
    SET is_active = COALESCE($2, is_active),
        fleet_id  = COALESCE($3, fleet_id)
    WHERE id = $1
      AND deleted_at IS NULL
"""

SOFT_DELETE_USER_SQL = """
    UPDATE app_user
    SET deleted_at = NOW()
    WHERE id = $1
      AND deleted_at IS NULL
"""

SELECT_USERS_SQL = """
    SELECT id, username, role, fleet_id, is_active, deleted_at, created_at
    FROM app_user
    WHERE deleted_at IS NULL
    ORDER BY id
"""

SELECT_ALL_USERS_SQL = SELECT_USERS_SQL

DEACTIVATE_USER_SQL = """
    UPDATE app_user
    SET is_active = FALSE
    WHERE id = $1
      AND deleted_at IS NULL
"""

UPDATE_PASSWORD_SQL = """
    UPDATE app_user
    SET password_hash = $2
    WHERE id = $1
      AND deleted_at IS NULL
"""
