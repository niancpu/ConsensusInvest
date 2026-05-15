import { useEffect, useState } from 'react';
import AnalysisPage from './features/analysis/AnalysisPage';
import DetailsPage from './features/details/DetailsPage';
import HistoryPage from './features/history/HistoryPage';
import HomePage from './features/home/HomePage';
import ReportPage from './features/reports/ReportPage';

function getRoute() {
  return {
    hash: window.location.hash,
    pathname: window.location.pathname,
  };
}

function App() {
  const [route, setRoute] = useState(getRoute);
  const routeKey = route.hash.split('?')[0];
  const isAnalysisRoute = routeKey === '#analysis' || route.pathname.startsWith('/analysis');
  const isReportRoute = routeKey === '#reports' || route.pathname.startsWith('/reports');
  const isHistoryRoute = routeKey === '#history' || route.pathname.startsWith('/history');
  const isDetailsRoute = routeKey === '#details' || route.pathname.startsWith('/details');

  useEffect(() => {
    const handleRouteChange = () => setRoute(getRoute());

    window.addEventListener('hashchange', handleRouteChange);
    window.addEventListener('popstate', handleRouteChange);

    return () => {
      window.removeEventListener('hashchange', handleRouteChange);
      window.removeEventListener('popstate', handleRouteChange);
    };
  }, []);

  if (isAnalysisRoute) {
    return <AnalysisPage />;
  }
  if (isReportRoute) {
    return <ReportPage />;
  }
  if (isHistoryRoute) {
    return <HistoryPage />;
  }
  if (isDetailsRoute) {
    return <DetailsPage />;
  }
  return <HomePage />;
}

export default App;
