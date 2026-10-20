// Crystal AI Website - Interactive Scripts

document.addEventListener('DOMContentLoaded', () => {
  initClipboardButtons();
  initHeroTabs();
  initCliTabs();
  initFaqAccordion();
  initMobileMenu();
  initLiveDemoEmbed();
});

// 1. Copy to clipboard
function initClipboardButtons() {
  const copyButtons = document.querySelectorAll('[data-copy-target]');
  copyButtons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      const targetId = btn.getAttribute('data-copy-target');
      const targetElement = document.getElementById(targetId);
      if (!targetElement) return;

      const text = targetElement.getAttribute('data-copy-text') || targetElement.innerText.trim();

      try {
        await navigator.clipboard.writeText(text);
        showCopyFeedback(btn);
      } catch (err) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showCopyFeedback(btn);
      }
    });
  });
}

function showCopyFeedback(btn) {
  const originalHtml = btn.innerHTML;
  btn.classList.add('text-zinc-200', 'bg-zinc-800');
  btn.innerHTML = `
    <svg class="w-3.5 h-3.5 inline-block mr-1 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
    </svg>
    <span class="text-emerald-400">Copied</span>
  `;

  setTimeout(() => {
    btn.innerHTML = originalHtml;
    btn.classList.remove('text-zinc-200', 'bg-zinc-800');
  }, 2000);
}

// 2. Hero Interactive Mockup Tabs
function initHeroTabs() {
  const tabBtns = document.querySelectorAll('.hero-tab-btn');
  const tabPanes = document.querySelectorAll('.hero-tab-pane');

  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');

      // Update active button state
      tabBtns.forEach((b) => {
        b.classList.remove('bg-zinc-800', 'text-white', 'border-zinc-700');
        b.classList.add('text-zinc-400', 'border-transparent', 'hover:text-zinc-200');
      });
      btn.classList.add('bg-zinc-800', 'text-white', 'border-zinc-700');
      btn.classList.remove('text-zinc-400', 'border-transparent');

      // Switch active pane
      tabPanes.forEach((pane) => {
        if (pane.id === `tab-${targetTab}`) {
          pane.classList.remove('hidden');
          pane.classList.add('animate-fadeIn');
        } else {
          pane.classList.add('hidden');
        }
      });
    });
  });
}

// 3. CLI Command Simulator Tabs
function initCliTabs() {
  const cliTabs = document.querySelectorAll('.cli-tab-btn');
  const cliPanes = document.querySelectorAll('.cli-pane');

  cliTabs.forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-cli-target');

      cliTabs.forEach((b) => {
        b.classList.remove('bg-zinc-800', 'text-white', 'border-zinc-700');
        b.classList.add('text-zinc-400', 'border-transparent', 'hover:text-zinc-300');
      });
      btn.classList.add('bg-zinc-800', 'text-white', 'border-zinc-700');
      btn.classList.remove('text-zinc-400', 'border-transparent');

      cliPanes.forEach((pane) => {
        if (pane.id === `cli-${target}`) {
          pane.classList.remove('hidden');
        } else {
          pane.classList.add('hidden');
        }
      });
    });
  });
}

// 4. FAQ Accordion
function initFaqAccordion() {
  const faqItems = document.querySelectorAll('.faq-item');

  faqItems.forEach((item) => {
    const trigger = item.querySelector('.faq-trigger');
    const content = item.querySelector('.faq-content');
    const icon = item.querySelector('.faq-icon');

    if (!trigger || !content) return;

    trigger.addEventListener('click', () => {
      const isOpen = !content.classList.contains('hidden');

      faqItems.forEach((other) => {
        const otherContent = other.querySelector('.faq-content');
        const otherIcon = other.querySelector('.faq-icon');
        if (otherContent) otherContent.classList.add('hidden');
        if (otherIcon) otherIcon.style.transform = 'rotate(0deg)';
      });

      if (!isOpen) {
        content.classList.remove('hidden');
        if (icon) icon.style.transform = 'rotate(180deg)';
      } else {
        content.classList.add('hidden');
        if (icon) icon.style.transform = 'rotate(0deg)';
      }
    });
  });
}

// 5. Mobile Menu
function initMobileMenu() {
  const toggleBtn = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');

  if (toggleBtn && mobileMenu) {
    toggleBtn.addEventListener('click', () => {
      mobileMenu.classList.toggle('hidden');
    });

    mobileMenu.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        mobileMenu.classList.add('hidden');
      });
    });
  }
}

// 6. Live Demo Iframe Lazy Loader
function initLiveDemoEmbed() {
  const loadBtn = document.getElementById('load-live-demo-btn');
  const container = document.getElementById('demo-iframe-container');
  const placeholder = document.getElementById('demo-placeholder');

  if (loadBtn && container && placeholder) {
    loadBtn.addEventListener('click', () => {
      placeholder.classList.add('hidden');
      container.classList.remove('hidden');
      container.innerHTML = `
        <iframe 
          src="https://blaid.duckdns.org" 
          class="w-full h-[650px] border-0 rounded-b-xl bg-black"
          title="Crystal Live Web Demo"
          allow="clipboard-read; clipboard-write;"
          loading="lazy"
        ></iframe>
      `;
    });
  }
}
