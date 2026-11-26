import { z } from "zod";

export const TeamStatSchema = z.object({
  season: z.string(),
  played: z.number().int().nonnegative(),
  wins: z.number().int().nonnegative(),
  draws: z.number().int().nonnegative(),
  losses: z.number().int().nonnegative(),
  goals_for: z.number().int().nonnegative(),
  goals_against: z.number().int().nonnegative(),
  xg_for_avg: z.number(),
  xg_against_avg: z.number(),
  shots_avg: z.number(),
  possession_avg: z.number(),
  recent_form: z.string(),
});

export const TeamSchema = z.object({
  id: z.number().int(),
  external_id: z.string(),
  name: z.string(),
  short_name: z.string(),
  crest_url: z.string().nullable().optional(),
  league_code: z.string(),
  elo_rating: z.number(),
  stats: TeamStatSchema.nullable().optional(),
});

export const PredictionSummarySchema = z.object({
  prob_home: z.number().min(0).max(1),
  prob_draw: z.number().min(0).max(1),
  prob_away: z.number().min(0).max(1),
  prob_over_25: z.number().min(0).max(1),
  prob_under_25: z.number().min(0).max(1),
  prob_btts_yes: z.number().min(0).max(1),
  prob_btts_no: z.number().min(0).max(1),
  expected_home_goals: z.number(),
  expected_away_goals: z.number(),
  predicted_home_score: z.number().int(),
  predicted_away_score: z.number().int(),
  confidence_score: z.number(),
  explanation_text: z.string(),
});

export const MatchSchema = z.object({
  id: z.number().int(),
  external_id: z.string(),
  league_code: z.string(),
  league_name: z.string(),
  match_date: z.string(),
  status: z.enum(["SCHEDULED", "LIVE", "FINISHED", "POSTPONED", "CANCELLED"]),
  home_score: z.number().int().nullable().optional(),
  away_score: z.number().int().nullable().optional(),
  venue: z.string().nullable().optional(),
  home_team: TeamSchema,
  away_team: TeamSchema,
  prediction: PredictionSummarySchema.nullable().optional(),
});

export const SyncStatusSchema = z.object({
  data_delayed: z.boolean(),
  delay_label: z.string().nullable().optional(),
  last_sync_status: z.string().nullable().optional(),
  last_sync_at: z.string().nullable().optional(),
  last_success_at: z.string().nullable().optional(),
  last_sync_age_minutes: z.number().int().nullable().optional(),
  source: z.string().nullable().optional(),
});

export const HealthSchema = z.object({
  status: z.string(),
  service: z.string(),
  cache_backend: z.string(),
  cache_ok: z.boolean(),
  sync_status: SyncStatusSchema.optional(),
});
