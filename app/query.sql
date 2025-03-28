-- name: InsertUser :one
INSERT INTO users (id,username, password_hash) VALUES (?,?,?)
RETURNING id;

-- name: InsertAnonymousUser :exec
INSERT OR IGNORE INTO users (id, username) VALUES (?, "anonymous");

-- name: InsertOIDCUser :exec
INSERT INTO oidc_users (user_id, client_id, user_sub) VALUES (?,?,?);

-- name: InsertPaste :one
INSERT INTO pastes (id, owner_id,slug,content,content_format,visibility,expires_at) VALUES (?,?,?,?,?,?,?)
RETURNING id;

-- name: InsertPasteAttachment :one
INSERT INTO attachments (id, paste_id,slug,mime_type,size,checksum) VALUES (?,?,?,?,?,?)
RETURNING id;

-- name: GetUserByID :one
SELECT * FROM users
WHERE id = ? LIMIT 1;

-- name: GetUserByUsername :one
SELECT * FROM users
WHERE username = ? LIMIT 1;

-- name: GetUserByOIDC :one
SELECT u.* FROM oidc_users AS o
INNER JOIN users AS u ON u.id = o.user_id
WHERE client_id = ? AND user_sub = ?
LIMIT 1;

-- name: GetLatestPublicPastes :many
SELECT p.id, p.owner_id, p.slug, p.created_at, users.username FROM pastes as p
INNER JOIN users ON users.id = p.owner_id
WHERE (
    p.visibility = 'public'
    AND (p.expires_at IS NULL OR p.expires_at > CURRENT_TIMESTAMP)
)
ORDER BY p.id DESC
LIMIT ?;

-- name: GetLatestPastesByUser :many
SELECT p.id, p.owner_id, p.slug, p.created_at, p.visibility FROM pastes as p
INNER JOIN users ON users.id = p.owner_id
WHERE username = sqlc.arg(username) AND (
    (visibility = 'public' AND NOT p.owner_id = sqlc.arg(current_user_id))
    OR
    (p.owner_id = sqlc.arg(current_user_id))
) AND (p.expires_at IS NULL OR p.expires_at > CURRENT_TIMESTAMP)
ORDER BY p.id DESC;

-- name: GetPasteBySlug :one
SELECT p.* FROM pastes as p
INNER JOIN users AS u ON u.id = p.owner_id
WHERE (
    (u.username = sqlc.arg(username) AND p.slug = sqlc.arg(paste_slug))
    AND
       (
           (p.visibility IN ('public', 'unlisted') AND NOT p.owner_id = sqlc.arg(current_user_id))
           OR
           (p.owner_id = sqlc.arg(current_user_id))
       )
    AND (p.expires_at IS NULL OR p.expires_at > CURRENT_TIMESTAMP)
    )
LIMIT 1;

-- name: GetPastePathParts :one
SELECT p.slug, u.username FROM pastes as p
INNER JOIN users AS u ON u.id = p.owner_id
WHERE p.id = ?
LIMIT 1;

-- name: GetAttachmentsByPasteID :many
SELECT a.* FROM attachments AS a
INNER JOIN pastes AS p ON a.paste_id = p.id
WHERE (
    a.paste_id = ?
    AND
    (p.expires_at IS NULL OR p.expires_at > CURRENT_TIMESTAMP)
);

-- name: GetAttachmentBySlug :one
SELECT a.* FROM attachments as a
INNER JOIN pastes AS p ON a.paste_id = p.id
INNER JOIN users AS u ON u.id = p.owner_id
WHERE
    (
        (u.username = sqlc.arg(username) AND p.slug = sqlc.arg(paste_slug) AND a.slug = sqlc.arg(attachment_slug))
        AND
        (
            (p.visibility IN ('public', 'unlisted') AND NOT p.owner_id = sqlc.arg(current_user_id))
            OR
            (p.owner_id = sqlc.arg(current_user_id))
        )
        AND (p.expires_at IS NULL OR p.expires_at > CURRENT_TIMESTAMP)
    )
LIMIT 1;
