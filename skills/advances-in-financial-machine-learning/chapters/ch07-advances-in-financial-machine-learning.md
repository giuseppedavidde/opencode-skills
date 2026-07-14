# Chapter 7: Cross-Validation in Finance

## Core Idea
Standard k-fold cross-validation, the workhorse of ML, fails in finance and produces false discoveries. The reason is **leakage**: financial features are serially correlated and labels are computed over overlapping windows, so observations placed in different folds share information. CV cannot detect the resulting overfitting — it actually *contributes* to it via hyper-parameter tuning. The fix is **purged k-fold CV** with embargoing.

## Frameworks Introduced
- **The Goal of CV**: estimate the generalization error by partitioning into train/test sets preventing leakage; in finance used both for hyper-parameter tuning and (Ch.12) backtesting.
- **Why K-Fold CV Fails in Finance**: (1) observations are not IID — serially correlated features and overlapping labels mean X_t ≈ X_{t+1} and Y_t ≈ Y_{t+1}; placing them in different folds leaks. (2) The testing set is reused many times (model development), causing multiple testing and selection bias (revisited in Ch.11-13).
- **Purging**: drop from the training set every observation whose label Y_i overlaps in time with any label in the testing set. Three sufficient overlap conditions on intervals [t_{j,0}, t_{j,1}]. Leakage, when present, inflates performance as k -> T; purging detects this by capping the spurious improvement.
- **Embargo**: beyond purging, drop training observations that immediately follow every test set (one-sided, since pre-test training labels contain no future info). Implement by extending Y_j = f[[t_{j,0}, t_{j,1}+h]] with a small embargo h ≈ 0.01 T before purging. Confirm by checking performance no longer improves indefinitely as k grows.
- **PurgedKFold class (Snippet 7.3)**: extends sklearn's KFold to prevent leakage during hyper-parameter fitting, backtesting, and performance evaluation.

## Key Concepts
- Leakage from irrelevant features produces false discoveries; leakage from predictive features merely inflates an already-valuable strategy.
- Leakage requires the *joint* overlap (X_i,Y_i) ≈ (X_j,Y_j); X_i ≈ X_j alone is not leakage if Y_i and Y_j are independent.
- Reducing leakage: (1) drop overlapping training obs; (2) early stopping / bagging with max_samples = average uniqueness; (3) sequential bootstrap (Ch.4).
- Shuffling before k-fold defeats the purpose in finance because it spatters redundant observations across folds.

## Anti-patterns
- **Shuffling the dataset** before k-fold CV — guarantees leakage.
- Trusting **out-of-bag accuracy** from bagging in finance — inflated because redundant obs land in both training and OOB samples.
- Recycling the test set across many model configurations — selection bias.
- Using sklearn's `cross_val_score` directly — affected by known bugs (issues #6231, #9144): scoring functions ignore `classes_` and weights are not passed to `log_loss`. Use the custom `cvScore` (Snippet 7.4).
- Citing k-fold CV evidence in a finance paper and assuming the result is sound.

## Key Takeaways
- Standard k-fold CV virtually guarantees leakage on non-IID financial features.
- Always purge overlapping labels from the training set and add an embargo on post-test observations.
- A small embargo h ≈ 0.01 T usually suffices; verify by checking that performance no longer grows with k.
- Until sklearn fixes its CV bugs, use the book's `PurgedKFold` and `cvScore` wrappers.