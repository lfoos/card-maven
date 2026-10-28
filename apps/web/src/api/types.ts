/** Friendly names for the generated API schema (src/api/schema.d.ts). */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Item = Schemas["ItemOut"];
export type ItemPage = Schemas["ItemPageOut"];
export type ItemImage = Schemas["ImageOut"];
export type NewItem = Schemas["NewItem"];
export type ItemChanges = Schemas["ItemChanges"];
export type CardIdentity = Schemas["CardIdentity"];
export type Money = Schemas["MoneyOut"];
export type SetSuggestion = Schemas["SetSuggestionOut"];
export type PlayerSuggestion = Schemas["PlayerSuggestionOut"];
export type Parallel = Schemas["ParallelOut"];
export type UploadStarted = Schemas["UploadStartedOut"];
export type Me = Schemas["MeOut"];
export type FieldError = Schemas["FieldError"];

export type ItemSort = "newest" | "oldest" | "year_desc" | "year_asc" | "name";
export type Condition = "raw" | "graded";
export type ImageKind = "front" | "back";

export interface ItemFilters {
  q?: string;
  sport?: string;
  year?: number;
  brand?: string;
  condition?: Condition;
  sort?: ItemSort;
}

export type ItemMarket = Schemas["ItemMarketOut"];
export type Comp = Schemas["CompOut"];
export type Ask = Schemas["AskOut"];
export type Estimate = Schemas["EstimateOut"];
export type SyncJob = Schemas["SyncJobOut"];
export type ManualSale = Schemas["ManualSale"];
export type SalesAdded = Schemas["SalesAddedOut"];
export type Grader = Schemas["Grader"];
export type SaleType = Schemas["SaleType"];
