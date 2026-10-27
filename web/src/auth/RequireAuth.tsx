import { Navigate, Outlet, useLocation } from "react-router";
import { useLoggedIn } from "./useSession";

export function RequireAuth() {
  const loggedIn = useLoggedIn();
  const location = useLocation();
  if (!loggedIn) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}
