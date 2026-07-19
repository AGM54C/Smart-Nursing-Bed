module.exports = {
    apps: [{
        name: 'smart-nursing-bed',
        script: 'server.js',
        cwd: '/opt/smart-nursing-bed',
        instances: 1,
        autorestart: true,
        watch: false,
        max_memory_restart: '512M',
        env: {
            NODE_ENV: 'production',
            PORT: 3000
        },
        log_date_format: 'YYYY-MM-DD HH:mm:ss',
        error_file: '/var/log/smart-nursing-bed/error.log',
        out_file: '/var/log/smart-nursing-bed/out.log',
        merge_logs: true,
        log_rotate: true
    }]
};
