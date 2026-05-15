type NavKey = 'home' | 'analysis' | 'reports' | 'history';

const navItems: Array<{ key: NavKey; label: string; href: string }> = [
  { key: 'home', label: '主页', href: '#home' },
  { key: 'analysis', label: '分析', href: '#analysis' },
  { key: 'reports', label: '资讯报告', href: '#reports' },
  { key: 'history', label: '历史', href: '#history' },
];

function GlobalNav({ active, className }: { active?: NavKey; className: string }) {
  return (
    <header className={className}>
      <a className="brand" href="/">
        ConsensusInvest
      </a>
      <nav className="nav-links" aria-label="Primary">
        {navItems.map((item) => (
          <a className={item.key === active ? 'nav-link active' : 'nav-link'} href={item.href} key={item.key}>
            {item.label}
          </a>
        ))}
      </nav>
    </header>
  );
}

export default GlobalNav;
