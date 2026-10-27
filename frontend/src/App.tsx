import { Dashboard } from "./pages/Dashboard";
import { StageView } from "./pages/StageView";
import { api } from "./services/api";

export default function App() {
  // ?view=stage: full-window presenter for TikTok LIVE Studio / OBS capture.
  if (new URLSearchParams(window.location.search).get("view") === "stage") return <StageView />;
  return <Dashboard client={api} />;
}
