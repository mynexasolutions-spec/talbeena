(function () {
    // ── Hero slideshow ──
    const slides = document.querySelectorAll('.hero-slide');
    const dots = document.querySelectorAll('.hero-dot');
    if (slides.length) {
      let current = 0;
      let timer;
      function goTo(index) {
        slides.forEach(s => s.classList.remove('active'));
        dots.forEach(d => d.classList.remove('active'));
        slides[index].classList.add('active');
        dots[index].classList.add('active');
        current = index;
        resetTimer();
      }
      function next() { goTo((current + 1) % slides.length); }
      function resetTimer() { clearInterval(timer); timer = setInterval(next, 5000); }
      dots.forEach(dot => {
        dot.addEventListener('click', function () { goTo(parseInt(this.dataset.index)); });
      });
      resetTimer();
    }

    // ── Testimonial carousel arrows ──
    const track = document.getElementById('testTrack');
    const prevBtn = document.getElementById('testPrev');
    const nextBtn = document.getElementById('testNext');
    if (track && prevBtn && nextBtn) {
      const scrollAmount = () => {
        const card = track.querySelector('.testimonial-card');
        return card ? card.offsetWidth + 24 : 320;
      };
      prevBtn.addEventListener('click', () => { track.scrollBy({ left: -scrollAmount(), behavior: 'smooth' }); });
      nextBtn.addEventListener('click', () => { track.scrollBy({ left: scrollAmount(), behavior: 'smooth' }); });
    }

    // ── Scroll fade-in ──
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12 });
      document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));
    } else {
      document.querySelectorAll('.fade-in').forEach(el => el.classList.add('visible'));
    }

    // ── Video Carousel ──
    const carousel = document.querySelector('.video-carousel');
    const carouselItems = document.querySelectorAll('.video-item');
    const carouselVideos = document.querySelectorAll('.carousel-video');
    const carouselDots = document.querySelectorAll('.carousel-dots .dot');
    const carouselPrevBtn = document.querySelector('.carousel-arrow-prev');
    const carouselNextBtn = document.querySelector('.carousel-arrow-next');

    if (carousel && carouselItems.length > 0) {
      let currentIndex = 0;
      let autoplayTimer = null;

      function showSlide(index) {
        carouselItems.forEach((item, i) => {
          item.classList.toggle('active', i === index);
        });
        carouselDots.forEach((dot, i) => {
          dot.classList.toggle('active', i === index);
        });
        currentIndex = index;

        // Pause all videos and play current one
        carouselVideos.forEach((video, i) => {
          if (i === index) {
            video.play().catch(() => {});
          } else {
            video.pause();
          }
        });

        resetAutoplay();
      }

      function nextSlide() {
        showSlide((currentIndex + 1) % carouselItems.length);
      }

      function prevSlide() {
        showSlide((currentIndex - 1 + carouselItems.length) % carouselItems.length);
      }

      function resetAutoplay() {
        clearTimeout(autoplayTimer);
        const currentVideo = carouselVideos[currentIndex];
        if (currentVideo && !currentVideo.muted) {
          return; // Don't auto-advance if audio is on
        }

        // Auto-play next slide when video ends
        currentVideo.onended = () => {
          nextSlide();
        };

        // Fallback timer (120 seconds per video)
        autoplayTimer = setTimeout(nextSlide, 120000);
      }

      // Arrow button listeners
      if (carouselPrevBtn) carouselPrevBtn.addEventListener('click', prevSlide);
      if (carouselNextBtn) carouselNextBtn.addEventListener('click', nextSlide);

      // Dot navigation
      carouselDots.forEach((dot, index) => {
        dot.addEventListener('click', () => showSlide(index));
      });

      // Unmute button functionality
      const carouselUnmuteButtons = document.querySelectorAll('.video-btn-unmute');
      carouselUnmuteButtons.forEach((btn, index) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const video = carouselVideos[index];
          video.muted = !video.muted;
          btn.classList.toggle('muted', !video.muted);

          if (!video.muted) {
            clearTimeout(autoplayTimer);
          } else {
            resetAutoplay();
          }
        });
      });

      // Touch/Swipe support for mobile
      let touchStartX = 0;
      let touchEndX = 0;

      carousel.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
      });

      carousel.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
      });

      function handleSwipe() {
        if (touchStartX - touchEndX > 50) {
          nextSlide();
        } else if (touchEndX - touchStartX > 50) {
          prevSlide();
        }
      }

      // Initialize first slide
      showSlide(0);
    }
  })();


  // ── Lazy video loading (IntersectionObserver) ──
  const lazyVideos = document.querySelectorAll('video[data-src]');
  if ('IntersectionObserver' in window && lazyVideos.length) {
    const videoObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const v = entry.target;
        v.src = v.dataset.src;
        v.removeAttribute('data-src');
        v.load();
        const item = v.closest('.video-item');
        if (item && item.classList.contains('active')) {
          v.addEventListener('loadeddata', () => { v.play().catch(() => {}); }, { once: true });
        }
        videoObserver.unobserve(v);
      });
    }, { rootMargin: '200px' });
    lazyVideos.forEach(v => videoObserver.observe(v));
  } else {
    lazyVideos.forEach(v => { v.src = v.dataset.src; v.removeAttribute('data-src'); });
  }
