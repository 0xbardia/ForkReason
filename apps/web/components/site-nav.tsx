"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { WalletButton } from "@/components/wallet-button";
import { BrandMark } from "@/components/brand-mark";

const LINKS = [
  { href: "/trace", label: "Trace" },
  { href: "/explore", label: "Explore" },
  { href: "/docs", label: "Docs" },
  { href: "/security", label: "Security" },
] as const;

const GITHUB_URL = "https://github.com/0xbardia/ForkReason";

export function SiteNav() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  // The nav gains its material only once the page has scrolled, so the hero
  // reads as open space rather than sitting under a bar.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Close the mobile menu on navigation.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const isActive = (href: string) =>
    pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <header
      className="site-nav"
      data-scrolled={scrolled}
      data-menu-open={menuOpen}
    >
      <a href="#main" className="sr-only">
        Skip to content
      </a>
      <div className="site-nav-inner layout">
        <Link href="/" className="brand" aria-label="ForkReason home">
          <BrandMark />
          <span className="brand-name">ForkReason</span>
        </Link>

        <nav
          className="nav-links"
          aria-label="Main"
          // Hidden from assistive tech when the mobile drawer is closed, because
          // the links are still reachable via the visible toggle.
          data-collapsed={menuOpen ? "false" : "true"}
        >
          <ul className="nav-list">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="nav-link"
                  aria-current={isActive(link.href) ? "page" : undefined}
                  data-active={isActive(link.href)}
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <a
                href={GITHUB_URL}
                className="nav-link"
                target="_blank"
                rel="noopener noreferrer"
              >
                GitHub
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </li>
          </ul>
        </nav>

        <div className="nav-actions">
          <WalletButton />
          <button
            type="button"
            className="nav-toggle"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="nav-toggle-bars" aria-hidden="true" data-open={menuOpen} />
          </button>
        </div>
      </div>

      <div id="mobile-nav" className="mobile-nav" data-open={menuOpen} hidden={!menuOpen}>
        <ul>
          {LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="mobile-nav-link"
                aria-current={isActive(link.href) ? "page" : undefined}
              >
                {link.label}
              </Link>
            </li>
          ))}
          <li>
            <a
              href={GITHUB_URL}
              className="mobile-nav-link"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
          </li>
        </ul>
      </div>
    </header>
  );
}