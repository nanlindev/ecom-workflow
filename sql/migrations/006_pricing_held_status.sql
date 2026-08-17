-- Allow informational hold recommendations (no Approve/Reject required).

ALTER TABLE pricing_recommendations DROP CONSTRAINT IF EXISTS pricing_recommendations_status_check;

ALTER TABLE pricing_recommendations
  ADD CONSTRAINT pricing_recommendations_status_check
  CHECK (status IN (
    'pending',
    'approved',
    'rejected',
    'applied',
    'skipped_test_mode',
    'held'
  ));
