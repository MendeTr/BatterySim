"""
Orchestrator Agent - Coordinates all specialist agents and makes final decisions.

This is the "boss" agent that:
1. Collects recommendations from all specialist agents
2. Resolves conflicts when agents disagree
3. Makes final optimization decisions
4. Handles veto-level overrides
5. Balances short-term vs long-term value

Unlike specialist agents (rule-based, fast), the orchestrator uses
LLM reasoning for complex trade-offs and edge cases.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from .base_agent import BaseAgent, AgentRecommendation, AgentAction, BatteryContext
from .value_calculator import ValueCalculator
import json


@dataclass
class OrchestratorDecision:
    """
    Final decision from orchestrator.

    This is what gets executed by the battery system.
    """
    action: AgentAction
    kwh: float
    reasoning: str
    contributing_agents: List[str]  # Which agents influenced this decision
    total_value_sek: float
    confidence: float
    metadata: Dict

    # Conflict resolution
    had_conflicts: bool = False
    rejected_recommendations: List[AgentRecommendation] = None

    def __post_init__(self):
        if self.rejected_recommendations is None:
            self.rejected_recommendations = []


class Orchestrator(BaseAgent):
    """
    Master orchestrator for multi-agent battery optimization.

    Coordinates specialist agents:
    - RealTimeOverrideAgent: Emergency responses (veto power)
    - PeakShavingAgent: Effect tariff optimization
    - ArbitrageAgent: Price-based trading
    - SolarAgent: Solar self-consumption (future)

    Decision process:
    1. Check for veto-level overrides (safety, emergencies)
    2. Collect recommendations from all agents
    3. If no conflicts, execute highest value recommendation
    4. If conflicts, use optimization logic to resolve
    5. Apply constraints (battery limits, reserves)
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        value_calculator: ValueCalculator,
        use_llm_for_conflicts: bool = False,
        llm_api_key: Optional[str] = None
    ):
        """
        Initialize orchestrator.

        Args:
            agents: List of specialist agents to coordinate
            value_calculator: Shared value calculator
            use_llm_for_conflicts: Use GPT for complex conflict resolution
            llm_api_key: OpenAI API key (if using LLM)
        """
        super().__init__("Orchestrator", enabled=True)
        self.agents = agents
        self.value_calculator = value_calculator
        self.use_llm = use_llm_for_conflicts
        self.llm_api_key = llm_api_key

        # Statistics
        self.decisions_count = 0
        self.conflicts_resolved = 0
        self.vetos_applied = 0

    def analyze(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Coordinate all agents and make final decision.

        Note: Returns AgentRecommendation for interface compatibility,
        but internally uses OrchestratorDecision for richer context.
        """
        decision = self.make_decision(context)

        if decision is None:
            return None

        # Convert to AgentRecommendation for interface compatibility
        return AgentRecommendation(
            agent_name=self.name,
            action=decision.action,
            kwh=decision.kwh,
            confidence=decision.confidence,
            value_sek=decision.total_value_sek,
            priority=1,
            reasoning=decision.reasoning,
            metadata={
                'contributing_agents': decision.contributing_agents,
                'had_conflicts': decision.had_conflicts,
                'rejected_count': len(decision.rejected_recommendations)
            }
        )

    def make_decision(self, context: BatteryContext) -> Optional[OrchestratorDecision]:
        """
        Main decision-making process.

        Returns OrchestratorDecision with full context.
        """
        self.decisions_count += 1

        # Step 1: Collect recommendations from all agents
        recommendations = []
        for agent in self.agents:
            if not agent.enabled:
                continue

            try:
                rec = agent.analyze(context)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                # Log error but continue with other agents
                print(f"Error in {agent.name}: {e}")
                continue

        # Step 2: Handle empty case
        if not recommendations:
            return None  # No action needed

        # Step 3: Check for veto-level overrides (highest priority)
        veto_rec = self._check_for_vetos(recommendations)
        if veto_rec:
            self.vetos_applied += 1
            return OrchestratorDecision(
                action=veto_rec.action,
                kwh=veto_rec.kwh,
                reasoning=f"VETO OVERRIDE: {veto_rec.reasoning}",
                contributing_agents=[veto_rec.agent_name],
                total_value_sek=veto_rec.value_sek,
                confidence=veto_rec.confidence,
                had_conflicts=len(recommendations) > 1,
                rejected_recommendations=[r for r in recommendations if r != veto_rec],
                metadata={'veto': True, 'veto_agent': veto_rec.agent_name}
            )

        # Step 4: Optimize ALL recommendations (even if no conflicts!)
        # CRITICAL: Must simulate outcomes to prevent peak creation
        if len(recommendations) == 1:
            # Single recommendation - still need to validate it's safe
            rec = recommendations[0]
            adjusted_value = self._calculate_true_value(context, rec)

            # If value becomes negative after constraints, REJECT IT!
            if adjusted_value < 0:
                # This action would be harmful - better to do nothing
                return None

            return OrchestratorDecision(
                action=rec.action,
                kwh=rec.kwh,
                reasoning=rec.reasoning,
                contributing_agents=[rec.agent_name],
                total_value_sek=adjusted_value,  # Use adjusted value!
                confidence=rec.confidence,
                had_conflicts=False,
                metadata={'optimized_value': adjusted_value, 'original_value': rec.value_sek}
            )

        # Step 5: Multiple recommendations - resolve conflicts with optimization
        self.conflicts_resolved += 1
        return self._resolve_conflicts(context, recommendations)

    def _check_for_vetos(self, recommendations: List[AgentRecommendation]) -> Optional[AgentRecommendation]:
        """
        Check if any recommendation has veto power.

        Veto recommendations override everything else (safety, emergencies).
        """
        veto_recs = [r for r in recommendations if r.is_veto]

        if not veto_recs:
            return None

        # If multiple vetos (very rare), pick highest priority
        return max(veto_recs, key=lambda r: (r.priority, r.value_sek))

    def _detect_conflicts(self, recommendations: List[AgentRecommendation]) -> List[Tuple[AgentRecommendation, AgentRecommendation]]:
        """
        Detect conflicting recommendations.

        Conflicts occur when:
        - Different actions recommended (charge vs discharge)
        - Same action but different amounts
        - Competing for same battery capacity
        """
        conflicts = []

        for i, rec1 in enumerate(recommendations):
            for rec2 in recommendations[i+1:]:
                # Different actions = conflict
                if rec1.action != rec2.action:
                    conflicts.append((rec1, rec2))
                # Same action but significantly different amounts = conflict
                elif abs(rec1.kwh - rec2.kwh) > 2.0:  # 2 kWh threshold
                    conflicts.append((rec1, rec2))

        return conflicts

    def _resolve_conflicts(self, context: BatteryContext, recommendations: List[AgentRecommendation]) -> OrchestratorDecision:
        """
        Resolve conflicts between agents using OPTIMIZATION WITH CONSTRAINTS.

        This is NOT a simple consolidator - it's an optimizer that:
        1. Simulates the outcome of each recommendation
        2. Applies constraints (peak limits, battery reserves, safety)
        3. Adjusts value based on side effects and hidden costs
        4. Picks the action that maximizes true economic value

        Key constraints:
        - Never create peaks during 06:00-23:00 (60 SEK/kW/month cost)
        - Maintain minimum battery reserve for emergencies
        - Don't charge during peak hours (would create grid import peak)
        - Prioritize self-consumption over export (överföringsavgift makes export poor)
        """
        # Strategy 1: Check if recommendations can be combined
        combined = self._try_combine_recommendations(context, recommendations)
        if combined:
            return combined

        # Strategy 2: OPTIMIZE - Simulate outcomes and apply constraints
        optimized_recs = []
        for rec in recommendations:
            # Calculate TRUE value by simulating outcome
            adjusted_value = self._calculate_true_value(context, rec)
            optimized_recs.append((adjusted_value, rec))

        optimized_recs.sort(key=lambda x: x[0], reverse=True)
        best_value, best_rec = optimized_recs[0]

        # Check if top 2 are very close (within 10%)
        if len(optimized_recs) > 1:
            second_value, second_rec = optimized_recs[1]
            if second_value > best_value * 0.9:  # Very close
                # Complex decision - could use LLM here
                if self.use_llm:
                    return self._llm_resolve(context, [best_rec, second_rec])
                else:
                    # Fall back to simple rule: peak shaving > arbitrage
                    if best_rec.agent_name == "PeakShavingAgent":
                        chosen = best_rec
                        rejected = [second_rec]
                    elif second_rec.agent_name == "PeakShavingAgent":
                        chosen = second_rec
                        rejected = [best_rec]
                    else:
                        chosen = best_rec
                        rejected = [second_rec]

                    return OrchestratorDecision(
                        action=chosen.action,
                        kwh=chosen.kwh,
                        reasoning=f"Conflict resolved: {chosen.agent_name} prioritized over {rejected[0].agent_name}. {chosen.reasoning}",
                        contributing_agents=[chosen.agent_name],
                        total_value_sek=chosen.value_sek,
                        confidence=chosen.confidence * 0.9,  # Slightly lower due to conflict
                        had_conflicts=True,
                        rejected_recommendations=rejected,
                        metadata={'resolution_method': 'rule_based', 'close_call': True}
                    )

        # Clear winner
        rejected = [r for r in recommendations if r != best_rec]
        return OrchestratorDecision(
            action=best_rec.action,
            kwh=best_rec.kwh,
            reasoning=best_rec.reasoning,
            contributing_agents=[best_rec.agent_name],
            total_value_sek=best_rec.value_sek,
            confidence=best_rec.confidence,
            had_conflicts=True,
            rejected_recommendations=rejected,
            metadata={'resolution_method': 'priority_value_based'}
        )

    def _calculate_true_value(self, context: BatteryContext, rec: AgentRecommendation) -> float:
        """
        Calculate the TRUE economic value of a recommendation by simulating its outcome.

        This applies CONSTRAINTS and deducts costs from side effects:
        - Peak creation cost (60 SEK/kW/month)
        - Battery degradation cost
        - Opportunity costs

        Returns adjusted value in SEK (can be negative if action is harmful!)
        """
        from .base_agent import AgentAction

        # Start with agent's claimed value
        value = rec.value_sek

        # Simulate grid import after this action
        simulated_grid_import = context.grid_import_kw

        if rec.action == AgentAction.CHARGE:
            # Charging increases grid import
            simulated_grid_import += rec.kwh

        elif rec.action == AgentAction.DISCHARGE:
            # Discharging reduces grid import
            simulated_grid_import -= rec.kwh
            simulated_grid_import = max(0, simulated_grid_import)

        elif rec.action == AgentAction.EXPORT:
            # Export doesn't change grid import (already > 0)
            pass

        # CONSTRAINT 1: Check for peak creation (CRITICAL!)
        if context.is_measurement_hour:
            # Would this create or worsen a peak?
            current_threshold = context.peak_threshold_kw

            # If we're already in top 3, any increase is bad
            if len(context.top_n_peaks) >= 3 and simulated_grid_import > current_threshold:
                # Calculate peak cost: (new_peak - current_threshold) × 60 SEK/kW/month
                peak_increase_kw = simulated_grid_import - current_threshold
                monthly_peak_cost = peak_increase_kw * self.value_calculator.effect_tariff
                daily_peak_cost = monthly_peak_cost / 30

                # Deduct from value (this is a COST, not benefit!)
                value -= daily_peak_cost

                # If peak cost > claimed benefit, this action is NET NEGATIVE!
                if daily_peak_cost > rec.value_sek:
                    # Mark this as a bad decision
                    value = -daily_peak_cost

            # Even if not in top 3 yet, charging above threshold is risky
            elif rec.action == AgentAction.CHARGE and simulated_grid_import > current_threshold * 1.1:
                # Penalty for risky behavior (might become top 3 later)
                value *= 0.5  # 50% penalty for risk

        # CONSTRAINT 2: Battery reserve (don't drain below safe level)
        if rec.action == AgentAction.DISCHARGE:
            soc_after = context.soc_kwh - rec.kwh
            if soc_after < context.min_soc_kwh + 2.0:  # Within 2 kWh of minimum
                # Penalty for cutting it close
                value *= 0.7

        # CONSTRAINT 3: Opportunity cost (using battery now = can't use later)
        # If we discharge now for low value, might miss high-value opportunity later
        if rec.action == AgentAction.DISCHARGE and rec.priority >= 3:  # Low/medium priority
            # Check if upcoming hours have higher prices (opportunity cost)
            if context.spot_forecast and len(context.spot_forecast) > 6:
                avg_future_price = sum(context.spot_forecast[1:7]) / 6
                current_price = context.spot_price_sek_kwh
                if avg_future_price > current_price * 1.3:  # 30% higher later
                    # Penalize using battery now
                    value *= 0.8

        return value

    def _try_combine_recommendations(self, context: BatteryContext, recommendations: List[AgentRecommendation]) -> Optional[OrchestratorDecision]:
        """
        Try to combine compatible recommendations.

        Example: Peak shaving discharge + self-consumption discharge
        can be combined into a single larger discharge that achieves both goals.
        """
        # Group by action type
        by_action = {}
        for rec in recommendations:
            if rec.action not in by_action:
                by_action[rec.action] = []
            by_action[rec.action].append(rec)

        # If all recommendations are the same action, combine them
        if len(by_action) == 1:
            action = list(by_action.keys())[0]
            recs = by_action[action]

            # Take maximum kwh (not sum - they overlap)
            total_kwh = max(r.kwh for r in recs)

            # Check if combined action is feasible
            if action == AgentAction.DISCHARGE:
                available = context.soc_kwh - context.min_soc_kwh
                if total_kwh > available:
                    total_kwh = available

                if total_kwh < 0.5:
                    return None  # Can't combine, not enough battery

            elif action == AgentAction.CHARGE:
                room = context.capacity_kwh - context.soc_kwh
                if total_kwh > room:
                    total_kwh = room

                if total_kwh < 0.5:
                    return None  # Can't combine, not enough room

            # Calculate combined value
            total_value = sum(r.value_sek for r in recs)
            avg_confidence = sum(r.confidence for r in recs) / len(recs)
            contributing = [r.agent_name for r in recs]

            combined_reasoning = f"Combined strategy from {', '.join(contributing)}: "
            combined_reasoning += " + ".join([r.reasoning[:50] + "..." for r in recs])

            return OrchestratorDecision(
                action=action,
                kwh=total_kwh,
                reasoning=combined_reasoning,
                contributing_agents=contributing,
                total_value_sek=total_value,
                confidence=avg_confidence,
                had_conflicts=False,
                metadata={'combined': True, 'num_agents': len(recs)}
            )

        return None  # Can't combine different actions

    def _llm_resolve(self, context: BatteryContext, recommendations: List[AgentRecommendation]) -> OrchestratorDecision:
        """
        Use LLM (GPT) to resolve complex conflicts.

        This would make an API call to GPT-4 with context and recommendations,
        asking it to choose the best option with reasoning.

        For now, placeholder - would implement if needed for very complex cases.
        """
        # TODO: Implement GPT-based conflict resolution
        # For now, fall back to simple rule
        return self._resolve_conflicts(context, recommendations)

    def explain_decision(self, context: BatteryContext, recommendation: AgentRecommendation) -> str:
        """
        Explain orchestrator's final decision.
        """
        metadata = recommendation.metadata

        explanation = f"""
## Orchestrator Decision

**Final Action:** {recommendation.action.value.upper()}
**Amount:** {recommendation.kwh:.1f} kWh
**Expected Value:** {recommendation.value_sek:.0f} SEK
**Confidence:** {recommendation.confidence * 100:.0f}%

**Contributing Agents:**
{chr(10).join(f'- {agent}' for agent in metadata['contributing_agents'])}

**Decision Process:**
"""

        if metadata.get('veto'):
            explanation += f"""
⚠️ **VETO OVERRIDE**
The {metadata['veto_agent']} issued a veto-level recommendation that overrides all other agents.
This is typically for safety-critical situations or emergencies.
"""
        elif metadata.get('combined'):
            explanation += f"""
✓ **COMBINED STRATEGY**
Successfully combined recommendations from {metadata['num_agents']} agents into a single action
that achieves multiple optimization goals simultaneously.
"""
        elif metadata.get('had_conflicts'):
            explanation += f"""
⚡ **CONFLICT RESOLVED**
Multiple agents made competing recommendations. Resolved using {metadata.get('resolution_method', 'unknown')} strategy.

Rejected {metadata['rejected_count']} alternative recommendation(s).
"""
        else:
            explanation += """
✓ **UNANIMOUS DECISION**
All agents agreed or only one agent made a recommendation.
"""

        explanation += f"""

**Reasoning:**
{recommendation.reasoning}

**Battery Impact:**
- Current SOC: {context.soc_kwh:.1f} kWh
- After action: {context.soc_kwh + (recommendation.kwh if recommendation.action == AgentAction.CHARGE else -recommendation.kwh):.1f} kWh

---
**Statistics:**
- Total decisions made: {self.decisions_count}
- Conflicts resolved: {self.conflicts_resolved}
- Vetos applied: {self.vetos_applied}
"""

        return explanation

    def get_performance_metrics(self) -> Dict:
        """Get orchestrator performance metrics."""
        base_metrics = super().get_performance_metrics()

        base_metrics.update({
            'decisions_count': self.decisions_count,
            'conflicts_resolved': self.conflicts_resolved,
            'vetos_applied': self.vetos_applied,
            'conflict_rate': self.conflicts_resolved / self.decisions_count if self.decisions_count > 0 else 0,
            'veto_rate': self.vetos_applied / self.decisions_count if self.decisions_count > 0 else 0
        })

        # Add agent-specific metrics
        base_metrics['agent_performance'] = {}
        for agent in self.agents:
            base_metrics['agent_performance'][agent.name] = agent.get_performance_metrics()

        return base_metrics

    def __repr__(self):
        return (f"Orchestrator(agents={len(self.agents)}, "
                f"decisions={self.decisions_count}, "
                f"conflicts={self.conflicts_resolved})")
