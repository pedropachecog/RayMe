# Settings - RayMe AI (True Dark)

- Status: `Canonical`
- Stitch screen ID: `projects/715592942983517637/screens/34251c7eceae44b6bcf68860dc6a3006`
- Original Stitch title: `Settings - RayMe AI (True Dark)`

## Purpose

This screen appears to configure RayMe integrations, model choices, runtime behavior, and account-level preferences.

## Primary Layout Regions

- Left navigation rail
- Header describing preferences and integrations
- LLM configuration section with server URL, API key, and model selection
- System settings section with contextual screen awareness and wake-word sensitivity controls
- Account and billing-style rows for plan, personal info, payment, and devices
- Danger zone section for irreversible account actions

## Likely User Tasks

- Connect or update the model provider configuration
- Choose a preferred model from a predefined list
- Change runtime behavior such as screen awareness or wake-word sensitivity
- Access account, subscription, payment, or device settings
- Review destructive-account controls

## Implementation Notes For GSD

- The settings surface mixes technical configuration and user-account management, so future implementation may benefit from internal section components.
- Sensitive values such as API keys need explicit handling in the eventual product implementation.
- The presence of provider and model controls suggests that provider configuration is part of the MVP experience rather than a hidden admin surface.
