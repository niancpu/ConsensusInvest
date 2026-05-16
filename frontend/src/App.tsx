import AnalysisPage from './features/analysis/AnalysisPage';
import DetailsPage from './features/details/DetailsPage';
import HistoryPage from './features/history/HistoryPage';
import HomePage from './features/home/HomePage';
import ReportPage from './features/reports/ReportPage';
import { useHashRoute } from './router';

function App() {
  const route = useHashRoute();

  switch (route.name) {
    case 'analysis':
      return <AnalysisPage />;
    case 'reports':
      return <ReportPage />;
    case 'history':
      return <HistoryPage />;
    case 'details':
      return <DetailsPage />;
    default:
      return <HomePage />;
  }
}

export default App;
