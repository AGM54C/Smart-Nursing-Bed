const jwt = require('jsonwebtoken');

function authMiddleware(req, res, next) {
    // JWT from Authorization header (standard)  OR  ?token= query param (for SSE / EventSource)
    const authHeader = req.headers.authorization;
    const queryToken = req.query.token;

    let rawToken = null;
    if (authHeader && authHeader.startsWith('Bearer ')) {
        rawToken = authHeader.split(' ')[1];
    } else if (queryToken) {
        rawToken = queryToken;
    }

    if (!rawToken) {
        return res.status(401).json({ error: '未授权访问，请先登录' });
    }

    try {
        const decoded = jwt.verify(rawToken, process.env.JWT_SECRET);
        req.user = decoded;
        next();
    } catch (err) {
        return res.status(401).json({ error: '登录已过期，请重新登录' });
    }
}

function adminOnly(req, res, next) {
    if (req.user.role !== 'admin' && req.user.role !== 'doctor') {
        return res.status(403).json({ error: '权限不足' });
    }
    next();
}

module.exports = { authMiddleware, adminOnly };
