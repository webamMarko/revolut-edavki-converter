/**
 * Confetti Animation
 *
 * Lightweight canvas-based confetti celebration effect.
 * Usage: launchConfetti(duration)
 */

(function(window) {
    'use strict';

    /**
     * Launch confetti animation
     * @param {number} duration - Animation duration in milliseconds (default: 2000)
     */
    function launchConfetti(duration = 2000) {
        const canvas = document.createElement('canvas');
        canvas.className = 'confetti-canvas';
        canvas.style.position = 'fixed';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '9999';
        document.body.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;

        const particles = [];
        const particleCount = 150;
        const colors = ['#0EA5E9', '#8B5CF6', '#EF4444', '#F59E0B', '#10B981', '#EC4899'];

        // Create particles
        for (let i = 0; i < particleCount; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height - canvas.height,
                r: Math.random() * 6 + 2,
                d: Math.random() * particleCount,
                color: colors[Math.floor(Math.random() * colors.length)],
                tilt: Math.random() * 10 - 10,
                tiltAngleIncremental: Math.random() * 0.07 + 0.05,
                tiltAngle: 0
            });
        }

        const startTime = Date.now();

        function draw() {
            const now = Date.now();
            const elapsed = now - startTime;

            if (elapsed > duration) {
                document.body.removeChild(canvas);
                return;
            }

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            particles.forEach((p, i) => {
                ctx.beginPath();
                ctx.lineWidth = p.r / 2;
                ctx.strokeStyle = p.color;
                ctx.moveTo(p.x + p.tilt + p.r, p.y);
                ctx.lineTo(p.x + p.tilt, p.y + p.tilt + p.r);
                ctx.stroke();

                // Update
                p.tiltAngle += p.tiltAngleIncremental;
                p.y += (Math.cos(p.d) + 3 + p.r / 2) / 2;
                p.tilt = Math.sin(p.tiltAngle - i / 3) * 15;

                if (p.y > canvas.height) {
                    p.y = -10;
                    p.x = Math.random() * canvas.width;
                }
            });

            requestAnimationFrame(draw);
        }

        draw();
    }

    // Export to window
    window.launchConfetti = launchConfetti;

})(window);
