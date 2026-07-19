/**
 * Pressure Ulcer Prediction Route
 * POST /api/pressure/predict
 * Uses current pressure grid + patient posture duration to predict ulcer risk and recommend repositioning
 */
const express = require('express');
const router = express.Router();
const { authMiddleware } = require('../middleware/auth');

// Body region definitions for 8x8 grid (row ranges, col ranges, region name)
const BODY_REGIONS = [
    { id: 'occiput',   name: '枕部',   rows: [0,1], cols: [2,5], riskWeight: 1.5, icon: '🔴' },
    { id: 'shoulder',  name: '肩胛',   rows: [1,2], cols: [1,6], riskWeight: 2.0, icon: '🟠' },
    { id: 'thoracic',  name: '胸背',   rows: [3,4], cols: [2,5], riskWeight: 1.2, icon: '🟡' },
    { id: 'sacrum',    name: '骶尾',   rows: [4,5], cols: [2,5], riskWeight: 3.0, icon: '🔴' },
    { id: 'heel_l',    name: '左足跟', rows: [6,7], cols: [2,3], riskWeight: 2.5, icon: '🟠' },
    { id: 'heel_r',    name: '右足跟', rows: [6,7], cols: [4,5], riskWeight: 2.5, icon: '🟠' },
];

function avgZone(grid, r1, r2, c1, c2) {
    let sum = 0, count = 0;
    for (let r = r1; r <= Math.min(r2, grid.length-1); r++)
        for (let c = c1; c <= Math.min(c2, (grid[r]||[]).length-1); c++) {
            sum += (grid[r][c] || 0); count++;
        }
    return count > 0 ? sum / count : 0;
}

// Calculate pressure risk score for each body region
function analyzePressureRisk(grid, postureMinutes = 60) {
    const regions = BODY_REGIONS.map(region => {
        const avgPressure = avgZone(grid, region.rows[0], region.rows[1], region.cols[0], region.cols[1]);
        const normPressure = Math.min(avgPressure / 4095, 1.0);
        // Risk = pressure × time factor × anatomical weight
        const timeFactor = Math.min(postureMinutes / 120, 2.0); // maxes at 2h
        const riskScore = normPressure * region.riskWeight * timeFactor;
        return {
            ...region, avgPressure: Math.round(avgPressure),
            normPressure: Math.round(normPressure * 100),
            riskScore: Math.round(riskScore * 100) / 100,
            riskLevel: riskScore > 1.5 ? 'high' : riskScore > 0.8 ? 'medium' : riskScore > 0.3 ? 'low' : 'safe',
        };
    });

    const maxRisk = Math.max(...regions.map(r => r.riskScore));
    const topRegion = regions.find(r => r.riskScore === maxRisk);

    // Time to next reposition (minutes) based on pressure intensity
    const avgOverallNorm = regions.reduce((s, r) => s + r.normPressure, 0) / regions.length / 100;
    const baseInterval = 120; // standard 2h
    const adjustedInterval = Math.max(30, baseInterval * (1 - avgOverallNorm * 0.5));
    const alreadyElapsed = postureMinutes;
    const minutesUntilTurn = Math.max(0, Math.round(adjustedInterval - alreadyElapsed));

    // Recommended next posture
    const POSTURE_ROTATION = {
        'supine':      { next: 'left_side',  label: '建议左侧卧 30°', icon: '↙' },
        'left_side':   { next: 'supine',     label: '建议恢复仰卧位', icon: '↑' },
        'right_side':  { next: 'left_side',  label: '建议转换左侧卧', icon: '↙' },
        'prone':       { next: 'supine',     label: '建议转为仰卧位', icon: '↑' },
        'sitting':     { next: 'supine',     label: '建议让患者平躺休息', icon: '↗' },
    };

    return {
        regions: regions.sort((a,b) => b.riskScore - a.riskScore),
        overall_risk: maxRisk > 1.5 ? 'high' : maxRisk > 0.8 ? 'medium' : maxRisk > 0.3 ? 'low' : 'safe',
        overall_score: Math.round(maxRisk * 100) / 100,
        top_risk_region: topRegion,
        minutes_until_turn: minutesUntilTurn,
        needs_immediate_turn: minutesUntilTurn === 0,
        recommended_posture: POSTURE_ROTATION,
        time_in_posture: postureMinutes,
        adjusted_interval: Math.round(adjustedInterval),
    };
}

// POST /api/pressure/predict
router.post('/predict', authMiddleware, (req, res) => {
    const { grid, posture = 'supine', posture_minutes = 60 } = req.body;
    if (!grid || !Array.isArray(grid)) return res.status(400).json({ error: 'grid is required' });
    const result = analyzePressureRisk(grid, posture_minutes);
    result.posture = posture;
    result.timestamp = new Date().toISOString();
    res.json(result);
});

// GET /api/pressure/schedule/:patient_id - Get today's repositioning schedule
router.get('/schedule/:patient_id', authMiddleware, (req, res) => {
    const db = req.app.locals.db;
    try {
        // Get latest vitals to know current posture and time
        const v = db.prepare(
            'SELECT sleep_posture, recorded_at FROM vitals WHERE patient_id=? ORDER BY recorded_at DESC LIMIT 1'
        ).get(req.params.patient_id);

        const posture = v?.sleep_posture || 'supine';
        const now = new Date();
        const schedule = [];
        // Generate next 4 turns
        const POSTURES = ['supine', 'left_side', 'supine', 'right_side'];
        for (let i = 0; i < 4; i++) {
            const t = new Date(now.getTime() + (i+1) * 2 * 3600000);
            schedule.push({
                index: i+1, posture: POSTURES[i % 4],
                time: t.toTimeString().slice(0,5),
                label: { supine:'仰卧位', left_side:'左侧卧30°', right_side:'右侧卧30°' }[POSTURES[i%4]],
                due_in_minutes: (i+1) * 120
            });
        }
        res.json({ current_posture: posture, recorded_at: v?.recorded_at, schedule });
    } catch(e) {
        res.status(500).json({ error: e.message });
    }
});

module.exports = router;
