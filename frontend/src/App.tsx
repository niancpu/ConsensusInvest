import { useEffect, useState, type ReactNode } from 'react';
import AnalysisPage from './features/analysis/AnalysisPage';
import DetailsPage from './features/details/DetailsPage';
import HistoryPage from './features/history/HistoryPage';
import HomePage from './features/home/HomePage';
import ReportPage from './features/reports/ReportPage';
import { type RouteName, useHashRoute } from './router';

function App() {
  const route = useHashRoute();
  const [visitedRoutes, setVisitedRoutes] = useState<Set<RouteName>>(() => new Set([route.name]));

  useEffect(() => {
    setVisitedRoutes((current) => {
      if (current.has(route.name)) {
        return current;
      }
      const next = new Set(current);
      next.add(route.name);
      return next;
    });
  }, [route.name]);

  const analysisTicker = route.name === 'analysis' ? route.query.get('ticker') : null;
  const analysisRunId = route.name === 'analysis' ? route.query.get('run') : null;

  return (
    <>
      <RouteSlot active={route.name === 'home'} mounted={visitedRoutes.has('home')}>
        <HomePage />
      </RouteSlot>
      <RouteSlot active={route.name === 'analysis'} mounted={visitedRoutes.has('analysis')}>
        <AnalysisPage routeTicker={analysisTicker} routeRunId={analysisRunId} />
      </RouteSlot>
      <RouteSlot active={route.name === 'reports'} mounted={visitedRoutes.has('reports')}>
        <ReportPage />
      </RouteSlot>
      <RouteSlot active={route.name === 'history'} mounted={visitedRoutes.has('history')}>
        <HistoryPage />
      </RouteSlot>
      <RouteSlot active={route.name === 'details'} mounted={visitedRoutes.has('details')}>
        <DetailsPage />
      </RouteSlot>
    </>
  );
}

function RouteSlot({
  active,
  children,
  mounted,
}: {
  active: boolean;
  children: ReactNode;
  mounted: boolean;
}) {
  if (!mounted) {
    return null;
  }

  return <div hidden={!active}>{children}</div>;
}

export default App;
