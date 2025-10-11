// Mobile-specific JavaScript

// Function to detect if device is mobile based on screen width
function isMobileWidth() {
    return window.innerWidth < 768;
}

// Function to detect if device is mobile (includes user agent for initial load)
function isMobile() {
    return isMobileWidth() || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// Function to update menu visibility based on screen width
function updateMenuVisibility() {
    const hamburgerMenu = document.getElementById('hamburger-menu');
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');

    if (isMobileWidth()) {
        // Mobile: hide sidebar, show hamburger
        if (sidebar) sidebar.style.display = 'none';
        if (mainContent) mainContent.style.marginLeft = '0';
        if (hamburgerMenu) hamburgerMenu.style.display = 'flex';
    } else {
        // Desktop: show sidebar, hide hamburger
        if (sidebar) sidebar.style.display = 'flex';
        if (mainContent) mainContent.style.marginLeft = '250px';
        if (hamburgerMenu) hamburgerMenu.style.display = 'none';
        // Close mobile overlay if open
        const mobileNavOverlay = document.getElementById('mobile-nav-overlay');
        if (mobileNavOverlay) mobileNavOverlay.classList.remove('active');
    }
}

// Redirect to mobile version if on nodes page
if (window.location.pathname === '/nodes' && isMobile()) {
    window.location.href = '/mobile/nodes';
}

// Redirect to mobile version if on alerts page
if (window.location.pathname === '/alerts' && isMobile()) {
    window.location.href = '/mobile/alerts';
}

// Redirect to mobile version if on processes page
if (window.location.pathname === '/processes' && isMobile()) {
    window.location.href = '/mobile/processes';
}

// Redirect to mobile version if on settings page
if (window.location.pathname === '/settings' && isMobile()) {
    window.location.href = '/mobile/settings';
}

// Redirect to mobile version if on triggers page
if (window.location.pathname === '/triggers' && isMobile()) {
    window.location.href = '/mobile/triggers';
}

// Redirect to mobile version if on users page
if (window.location.pathname === '/users' && isMobile()) {
    window.location.href = '/mobile/users';
}

// Redirect to mobile version if on zones page
if (window.location.pathname === '/zones' && isMobile()) {
    window.location.href = '/mobile/zones';
}

// Redirect to mobile version if on alert_config page
if (window.location.pathname === '/alert_config' && isMobile()) {
    window.location.href = '/mobile/alert_config';
}

// Mobile-specific enhancements
document.addEventListener('DOMContentLoaded', function() {
    // Initial menu visibility update
    updateMenuVisibility();

    // Add window resize listener for responsive behavior
    window.addEventListener('resize', updateMenuVisibility);

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
        hamburgerMenu.addEventListener('click', function(event) {
            event.stopImmediatePropagation();
            const isOpen = mobileNavOverlay.classList.contains('active');
            if (isOpen) {
                closeMobileMenu();
            } else {
                openMobileMenu();
            }
        });

        // Close menu on close button click
        if (closeNav) {
            closeNav.addEventListener('click', function(event) {
                event.stopImmediatePropagation();
                closeMobileMenu();
            });
        }

        // Close menu on overlay click (outside content)
        mobileNavOverlay.addEventListener('click', function(e) {
            e.stopImmediatePropagation();
            if (e.target === mobileNavOverlay) {
                closeMobileMenu();
            }
        });

        // Close menu on navigation link click
        const navLinks = mobileNavOverlay.querySelectorAll('a');
        navLinks.forEach(link => {
            link.addEventListener('click', function(event) {
                event.stopImmediatePropagation();
                closeMobileMenu();
            });
        });

        // ESC key to close menu
        document.addEventListener('keydown', function(e) {
            e.stopImmediatePropagation();
            if (e.key === 'Escape' && mobileNavOverlay.classList.contains('active')) {
                closeMobileMenu();
            }
        });
    }

    // Function to open mobile menu
    function openMobileMenu() {
        mobileNavOverlay.classList.add('active');
        mobileNavOverlay.setAttribute('aria-hidden', 'false');
        hamburgerMenu.setAttribute('aria-expanded', 'true');
        // Prevent body scroll
        document.body.style.overflow = 'hidden';
        // Focus management: focus first link
        const firstLink = mobileNavOverlay.querySelector('a');
        if (firstLink) firstLink.focus();
    }

    // Function to close mobile menu
    function closeMobileMenu() {
        mobileNavOverlay.classList.remove('active');
        mobileNavOverlay.setAttribute('aria-hidden', 'true');
        hamburgerMenu.setAttribute('aria-expanded', 'false');
        // Restore body scroll
        document.body.style.overflow = '';
        // Return focus to hamburger
        hamburgerMenu.focus();
    }
});