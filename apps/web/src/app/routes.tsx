import type { RouteObject } from "react-router";
import { RequireAuth } from "../auth/RequireAuth";
import { Layout } from "../components/Layout";
import { AuthCallbackPage } from "../pages/AuthCallbackPage";
import { CollectionPage } from "../pages/CollectionPage";
import { HomePage } from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { TrendsPage } from "../pages/TrendsPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: "collection",
        element: (
          <RequireAuth>
            <CollectionPage />
          </RequireAuth>
        ),
      },
      { path: "trends", element: <TrendsPage /> },
      { path: "auth/callback", element: <AuthCallbackPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
