// Mobile-specific JavaScript

// Function to detect if device is mobile
function isMobile() {
    return window.innerWidth < 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// Redirect to mobile version if on nodes page
if (window.location.pathname === '/nodes' && isMobile()) {
    window.location.href = '/mobile/nodes';
}

// Mobile-specific enhancements
document.addEventListener('DOMContentLoaded', function() {
    // Add touch-friendly interactions
    const cards = document.querySelectorAll('.node-card');
    cards.forEach(card => {
        card.addEventListener('touchstart', function() {
            this.style.transform = 'scale(0.98)';
        });

        card.addEventListener('touchend', function() {
            this.style.transform = '';
        });
    });

    // Prevent zoom on input focus for iOS
    const inputs = document.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.setAttribute('inputmode', 'text');
        });
    });

    // Auto-refresh for mobile (less frequent to save battery)
    if (typeof loadNodes === 'function') {
        setInterval(loadNodes, 30000); // 30 seconds instead of 10
    }

    // Hamburger menu functionality
    const hamburgerMenu = document.getElementById('hamburger-menu');
    const mobileNavOverlay = document.getElementById('mobile-nav-overlay');
    const closeNav = document.getElementById('close-nav');

    if (hamburgerMenu && mobileNavOverlay) {
        // Toggle menu on hamburger click
        hamburgerMenu.addEventListener('click', function() {
            mobileNavOverlay.classList.toggle('active');
        });

        // Close menu on close button click
        if (closeNav) {
            closeNav.addEventListener('click', function() {
                mobileNavOverlay.classList.remove('active');
            });
        }

        // Close menu on overlay click (outside content)
        mobileNavOverlay.addEventListener('click', function(e) {
            if (e.target === mobileNavOverlay) {
                mobileNavOverlay.classList.remove('active');
            }
        });

        // Close menu on navigation link click
        const navLinks = mobileNavOverlay.querySelectorAll('a');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                mobileNavOverlay.classList.remove('active');
            });
        });
    }
});