import { Dashboard } from "./pages/Dashboard";
import { api } from "./services/api";

export default function App() {
  return <Dashboard client={api} />;
}
