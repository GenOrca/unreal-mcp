// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.
// AnimGraph authoring — split out of MCPythonHelper.cpp.

#include "MCPythonHelper.h"
#include "MCPythonHelperInternal.h"
#include "Engine/SCS_Node.h"
#include "Engine/SimpleConstructionScript.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Widget.h"
#include "Components/PanelWidget.h"
#include "Editor.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Toolkits/AssetEditorToolkit.h"
#include "BlueprintEditor.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardData.h"
#include "BehaviorTree/BTCompositeNode.h"
#include "BehaviorTree/BTTaskNode.h"
#include "BehaviorTree/BTDecorator.h"
#include "BehaviorTree/BTService.h"
#include "BehaviorTreeEditor.h"
#include "BehaviorTreeGraphNode.h"
#include "BehaviorTreeGraph.h"
#include "BehaviorTreeGraphNode_Root.h"
#include "BehaviorTreeGraphNode_Composite.h"
#include "BehaviorTreeGraphNode_Task.h"
#include "BehaviorTreeGraphNode_Decorator.h"
#include "BehaviorTreeGraphNode_Service.h"
#include "BehaviorTreeGraphNode_SimpleParallel.h"
#include "BehaviorTreeGraphNode_SubtreeTask.h"
#include "EdGraphSchema_BehaviorTree.h"
#include "EdGraph/EdGraph.h"
#include "UObject/UObjectIterator.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
// Blueprint graph includes
#include "K2Node_Event.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_CallFunction.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_MacroInstance.h"
#include "K2Node_DynamicCast.h"
#include "K2Node_InputKey.h"
#include "K2Node_SpawnActorFromClass.h"
#include "EdGraphSchema_K2.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Engine/Blueprint.h"
#include "UObject/UnrealType.h"
#include "UObject/TextProperty.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
// AnimGraph authoring (editor-only AnimGraph module)
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimSequence.h"
#include "AnimGraphNode_StateMachine.h"
#include "AnimGraphNode_SequencePlayer.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_StateResult.h"
#include "AnimGraphNode_TransitionResult.h"
#include "AnimStateNode.h"
#include "AnimStateTransitionNode.h"
#include "AnimStateEntryNode.h"
#include "AnimationStateMachineGraph.h"
#include "Kismet/KismetMathLibrary.h"
// Editor viewport projection
#include "LevelEditorViewport.h"
#include "EditorViewportClient.h"
#include "SceneView.h"

// ─── AnimGraph authoring ─────────────────────────────────────────────────────

static UEdGraphPin* FirstVisiblePin(UEdGraphNode* Node, EEdGraphPinDirection Dir)
{
    if (!Node) return nullptr;
    for (UEdGraphPin* P : Node->Pins)
        if (P && !P->bHidden && P->Direction == Dir)
            return P;
    return nullptr;
}

template <typename T>
static T* FindNodeOfType(UEdGraph* Graph)
{
    if (!Graph) return nullptr;
    for (UEdGraphNode* N : Graph->Nodes)
        if (T* Hit = Cast<T>(N))
            return Hit;
    return nullptr;
}

// Add a Sequence Player playing Seq into Graph and link its pose output to PoseSinkInputPin (if given).
static UAnimGraphNode_SequencePlayer* SpawnSequencePlayer(UEdGraph* Graph, UAnimSequence* Seq,
    int32 X, int32 Y, UEdGraphPin* PoseSinkInputPin)
{
    FGraphNodeCreator<UAnimGraphNode_SequencePlayer> Creator(*Graph);
    UAnimGraphNode_SequencePlayer* Node = Creator.CreateNode(false);
    Node->Node.SetSequence(Seq);
    Node->Node.SetLoopAnimation(true);
    Node->NodePosX = X;
    Node->NodePosY = Y;
    Creator.Finalize();
    if (PoseSinkInputPin)
    {
        if (UEdGraphPin* PoseOut = FirstVisiblePin(Node, EGPD_Output))
            PoseOut->MakeLinkTo(PoseSinkInputPin);
    }
    return Node;
}

FString UMCPythonHelper::AddAnimGraphSequencePlayer(UAnimBlueprint* AnimBP,
    const FString& AnimSequencePath, bool bLinkToOutputPose)
{
    if (!AnimBP)
        return MakeJsonError(TEXT("Invalid AnimBlueprint."));

    UEdGraph* AnimGraph = FindGraphByName(AnimBP, TEXT("AnimGraph"));
    if (!AnimGraph)
        return MakeJsonError(TEXT("AnimGraph not found on this AnimBlueprint."));

    UAnimSequence* Seq = Cast<UAnimSequence>(StaticLoadObject(UAnimSequence::StaticClass(), nullptr, *AnimSequencePath));
    if (!Seq)
        return MakeJsonError(FString::Printf(TEXT("AnimSequence not found: %s"), *AnimSequencePath));

    UAnimGraphNode_Root* Root = FindNodeOfType<UAnimGraphNode_Root>(AnimGraph);
    UEdGraphPin* RootIn = Root ? FindPinByName(Root, TEXT("Result"), EGPD_Input) : nullptr;

    UAnimGraphNode_SequencePlayer* Player =
        SpawnSequencePlayer(AnimGraph, Seq, -400, 0, (bLinkToOutputPose && RootIn) ? RootIn : nullptr);

    FKismetEditorUtilities::CompileBlueprint(AnimBP);

    TSharedPtr<FJsonObject> R = MakeShareable(new FJsonObject());
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("node_name"), Player->GetName());
    R->SetStringField(TEXT("sequence"), Seq->GetPathName());
    R->SetBoolField(TEXT("linked_to_output"), bLinkToOutputPose && RootIn != nullptr);
    return SerializeJsonObj(R);
}

// Populate a transition's rule graph with: Get(SpeedVar) (Greater|Less) Threshold -> bCanEnterTransition.
// Map a comparison operator string to a UKismetMathLibrary double-comparison UFunction.
static UFunction* FindFloatCompareFunc(const FString& Op)
{
    FName FnName;
    if (Op == TEXT(">"))       FnName = FName(TEXT("Greater_DoubleDouble"));
    else if (Op == TEXT("<"))  FnName = FName(TEXT("Less_DoubleDouble"));
    else if (Op == TEXT(">=")) FnName = FName(TEXT("GreaterEqual_DoubleDouble"));
    else if (Op == TEXT("<=")) FnName = FName(TEXT("LessEqual_DoubleDouble"));
    else if (Op == TEXT("==")) FnName = FName(TEXT("EqualEqual_DoubleDouble"));
    else return nullptr;
    return UKismetMathLibrary::StaticClass()->FindFunctionByName(FnName);
}

// Populate a transition rule graph with: Get(Var) <Op> Value -> bCanEnterTransition.
static bool BuildFloatTransitionRule(UEdGraph* TransitionGraph, const FString& Var, const FString& Op, float Value)
{
    UAnimGraphNode_TransitionResult* Result = FindNodeOfType<UAnimGraphNode_TransitionResult>(TransitionGraph);
    if (!Result) return false;
    UEdGraphPin* CanEnter = FindPinByName(Result, TEXT("bCanEnterTransition"), EGPD_Input);
    if (!CanEnter) return false;
    UFunction* CmpFunc = FindFloatCompareFunc(Op);
    if (!CmpFunc) return false;

    FGraphNodeCreator<UK2Node_VariableGet> GetCreator(*TransitionGraph);
    UK2Node_VariableGet* GetNode = GetCreator.CreateNode(false);
    GetNode->VariableReference.SetSelfMember(FName(*Var));
    GetNode->NodePosX = -500;
    GetCreator.Finalize();

    FGraphNodeCreator<UK2Node_CallFunction> CmpCreator(*TransitionGraph);
    UK2Node_CallFunction* CmpNode = CmpCreator.CreateNode(false);
    CmpNode->SetFromFunction(CmpFunc);
    CmpNode->NodePosX = -250;
    CmpCreator.Finalize();

    UEdGraphPin* VarOut = FirstVisiblePin(GetNode, EGPD_Output);
    UEdGraphPin* PinA = FindPinByName(CmpNode, TEXT("A"), EGPD_Input);
    UEdGraphPin* PinB = FindPinByName(CmpNode, TEXT("B"), EGPD_Input);
    UEdGraphPin* CmpRet = FindPinByName(CmpNode, TEXT("ReturnValue"), EGPD_Output);
    if (VarOut && PinA) VarOut->MakeLinkTo(PinA);
    if (PinB) PinB->DefaultValue = FString::SanitizeFloat(Value);
    if (CmpRet) CmpRet->MakeLinkTo(CanEnter);
    return VarOut && PinA && CmpRet;
}

// Core builder shared by the generic and the locomotion-convenience UFUNCTIONs.
// Spec: { machine_name?, entry?, states:[{name, anim?}], transitions:[{from,to,var?,op?,value?}] }
static FString BuildStateMachineFromSpec(UAnimBlueprint* AnimBP, const TSharedPtr<FJsonObject>& Spec)
{
    UEdGraph* AnimGraph = FindGraphByName(AnimBP, TEXT("AnimGraph"));
    if (!AnimGraph)
        return MakeJsonError(TEXT("AnimGraph not found on this AnimBlueprint."));

    const TArray<TSharedPtr<FJsonValue>>* StatesJson = nullptr;
    if (!Spec->TryGetArrayField(TEXT("states"), StatesJson) || StatesJson->Num() == 0)
        return MakeJsonError(TEXT("Spec must contain a non-empty 'states' array."));

    // Resolve + validate every state's anim up front (fail before mutating the graph).
    struct FStateDef { FString Name; UAnimSequence* Seq; };
    TArray<FStateDef> StateDefs;
    for (const TSharedPtr<FJsonValue>& SV : *StatesJson)
    {
        const TSharedPtr<FJsonObject> SO = SV->AsObject();
        if (!SO.IsValid())
            return MakeJsonError(TEXT("Each entry in 'states' must be an object."));
        FString Name, AnimPath;
        if (!SO->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty())
            return MakeJsonError(TEXT("Each state needs a non-empty 'name'."));
        SO->TryGetStringField(TEXT("anim"), AnimPath);
        UAnimSequence* Seq = nullptr;
        if (!AnimPath.IsEmpty())
        {
            Seq = Cast<UAnimSequence>(StaticLoadObject(UAnimSequence::StaticClass(), nullptr, *AnimPath));
            if (!Seq)
                return MakeJsonError(FString::Printf(TEXT("State '%s': AnimSequence not found: %s"), *Name, *AnimPath));
        }
        StateDefs.Add({ Name, Seq });
    }

    TArray<TSharedPtr<FJsonValue>> Warnings;

    // State machine node, linked to the Output Pose.
    UAnimGraphNode_Root* Root = FindNodeOfType<UAnimGraphNode_Root>(AnimGraph);
    UEdGraphPin* RootIn = Root ? FindPinByName(Root, TEXT("Result"), EGPD_Input) : nullptr;

    FGraphNodeCreator<UAnimGraphNode_StateMachine> SMCreator(*AnimGraph);
    UAnimGraphNode_StateMachine* SMNode = SMCreator.CreateNode(false);
    SMNode->NodePosX = -350;
    SMCreator.Finalize();
    if (RootIn)
    {
        if (UEdGraphPin* SMOut = FirstVisiblePin(SMNode, EGPD_Output))
        {
            RootIn->BreakAllPinLinks();
            SMOut->MakeLinkTo(RootIn);
        }
    }

    TArray<UEdGraph*> Subs = SMNode->GetSubGraphs();
    UEdGraph* SMGraph = Subs.Num() ? Subs[0] : nullptr;
    if (!SMGraph)
        return MakeJsonError(TEXT("State machine graph was not created."));

    // States — each with a looping sequence player wired to the state result.
    TMap<FString, UAnimStateNode*> StateByName;
    int32 Col = 0;
    for (const FStateDef& SD : StateDefs)
    {
        FGraphNodeCreator<UAnimStateNode> Creator(*SMGraph);
        UAnimStateNode* State = Creator.CreateNode(false);
        Creator.Finalize();
        if (UEdGraph* Bound = State->GetBoundGraph())
            FBlueprintEditorUtils::RenameGraph(Bound, SD.Name);
        if (SD.Seq)
        {
#if ENGINE_MAJOR_VERSION > 5 || (ENGINE_MAJOR_VERSION == 5 && ENGINE_MINOR_VERSION >= 7)
            // UAnimStateNode::GetResultNodeInsideState() was added in UE 5.7.
            UAnimGraphNode_StateResult* SR = State->GetResultNodeInsideState();
#else
            // UE 5.6 and earlier: find the state result by scanning the bound graph.
            UAnimGraphNode_StateResult* SR = nullptr;
            if (UEdGraph* Bound = State->GetBoundGraph())
            {
                for (UEdGraphNode* N : Bound->Nodes)
                {
                    if ((SR = Cast<UAnimGraphNode_StateResult>(N)) != nullptr)
                        break;
                }
            }
#endif
            if (SR)
            {
                UEdGraphPin* SRIn = FindPinByName(SR, TEXT("Result"), EGPD_Input);
                SpawnSequencePlayer(State->GetBoundGraph(), SD.Seq, -400, 0, SRIn);
            }
        }
        State->NodePosX = Col * 350;
        State->NodePosY = 0;
        ++Col;
        StateByName.Add(SD.Name, State);
    }

    // Entry -> entry state (defaults to the first state).
    FString EntryName = StateDefs[0].Name;
    Spec->TryGetStringField(TEXT("entry"), EntryName);
    UAnimStateNode** EntryState = StateByName.Find(EntryName);
    if (!EntryState)
        return MakeJsonError(FString::Printf(TEXT("Entry state '%s' is not one of the states."), *EntryName));
    if (UAnimStateEntryNode* Entry = FindNodeOfType<UAnimStateEntryNode>(SMGraph))
    {
        UEdGraphPin* EntryOut = FirstVisiblePin(Entry, EGPD_Output);
        UEdGraphPin* StateIn = FirstVisiblePin(*EntryState, EGPD_Input);
        if (EntryOut && StateIn) EntryOut->MakeLinkTo(StateIn);
        else Warnings.Add(MakeShareable(new FJsonValueString(TEXT("Could not connect the entry node."))));
    }

    // Transitions, each with an optional float-comparison rule.
    int32 TransCount = 0;
    const TArray<TSharedPtr<FJsonValue>>* TransJson = nullptr;
    if (Spec->TryGetArrayField(TEXT("transitions"), TransJson))
    {
        for (const TSharedPtr<FJsonValue>& TV : *TransJson)
        {
            const TSharedPtr<FJsonObject> TO = TV->AsObject();
            if (!TO.IsValid()) continue;
            FString From, To;
            TO->TryGetStringField(TEXT("from"), From);
            TO->TryGetStringField(TEXT("to"), To);
            UAnimStateNode** FromState = StateByName.Find(From);
            UAnimStateNode** ToState = StateByName.Find(To);
            if (!FromState || !ToState)
                return MakeJsonError(FString::Printf(TEXT("Transition references unknown state(s): '%s' -> '%s'."), *From, *To));

            FGraphNodeCreator<UAnimStateTransitionNode> Creator(*SMGraph);
            UAnimStateTransitionNode* Trans = Creator.CreateNode(false);
            Creator.Finalize();
            Trans->CreateConnections(*FromState, *ToState);
            ++TransCount;

            FString Var, Op;
            if (TO->TryGetStringField(TEXT("var"), Var) && TO->TryGetStringField(TEXT("op"), Op))
            {
                double Value = 0.0;
                TO->TryGetNumberField(TEXT("value"), Value);
                if (!BuildFloatTransitionRule(Trans->GetBoundGraph(), Var, Op, (float)Value))
                    Warnings.Add(MakeShareable(new FJsonValueString(
                        FString::Printf(TEXT("Rule for %s->%s left at default (bad var/op?)."), *From, *To))));
            }
        }
    }

    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(AnimBP);
    FKismetEditorUtilities::CompileBlueprint(AnimBP);

    TSharedPtr<FJsonObject> R = MakeShareable(new FJsonObject());
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("state_machine"), SMNode->GetName());
    TArray<TSharedPtr<FJsonValue>> StateNames;
    for (const FStateDef& SD : StateDefs)
        StateNames.Add(MakeShareable(new FJsonValueString(SD.Name)));
    R->SetArrayField(TEXT("states"), StateNames);
    R->SetNumberField(TEXT("transition_count"), TransCount);
    R->SetArrayField(TEXT("warnings"), Warnings);
    return SerializeJsonObj(R);
}

FString UMCPythonHelper::BuildAnimStateMachine(UAnimBlueprint* AnimBP, const FString& SpecJson)
{
    if (!AnimBP)
        return MakeJsonError(TEXT("Invalid AnimBlueprint."));
    TSharedPtr<FJsonObject> Spec;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(SpecJson);
    if (!FJsonSerializer::Deserialize(Reader, Spec) || !Spec.IsValid())
        return MakeJsonError(TEXT("Failed to parse spec JSON."));
    return BuildStateMachineFromSpec(AnimBP, Spec);
}
