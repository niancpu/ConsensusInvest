import { useEffect, useState } from 'react';

export type RouteName = 'home' | 'analysis' | 'reports' | 'history' | 'details';

export type Route = {
  name: RouteName;
  hash: string;
  pathname: string;
  query: URLSearchParams;
};

function readRoute(): Route {
  const hash = window.location.hash;
  const [rawKey, rawQuery] = hash.split('?');
  const pathname = window.location.pathname;
  const query = new URLSearchParams(rawQuery ?? '');
  const name = resolveName(rawKey, pathname);
  return { name, hash, pathname, query };
}

function resolveName(hashKey: string, pathname: string): RouteName {
  if (hashKey === '#analysis' || pathname.startsWith('/analysis')) return 'analysis';
  if (hashKey === '#reports' || pathname.startsWith('/reports')) return 'reports';
  if (hashKey === '#history' || pathname.startsWith('/history')) return 'history';
  if (hashKey === '#details' || pathname.startsWith('/details')) return 'details';
  return 'home';
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener('hashchange', onChange);
    window.addEventListener('popstate', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
      window.removeEventListener('popstate', onChange);
    };
  }, []);
  return route;
}
