import { Outlet, type RouteObject } from "react-router";
import { RequireAuth } from "../auth/RequireAuth";
import { Layout } from "../components/Layout";
import { AuthCallbackPage } from "../pages/AuthCallbackPage";
import { CollectionPage } from "../features/collection/CollectionPage";
import { EditItemPage } from "../features/collection/EditItemPage";
import { ItemDetailPage } from "../features/collection/ItemDetailPage";
import { NewItemPage } from "../features/collection/NewItemPage";
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
            <Outlet />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <CollectionPage /> },
          { path: "new", element: <NewItemPage /> },
          { path: ":itemId", element: <ItemDetailPage /> },
          { path: ":itemId/edit", element: <EditItemPage /> },
        ],
      },
      { path: "trends", element: <TrendsPage /> },
      { path: "auth/callback", element: <AuthCallbackPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
