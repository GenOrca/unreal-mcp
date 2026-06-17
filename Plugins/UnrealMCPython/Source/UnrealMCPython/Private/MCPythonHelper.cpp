// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.

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

TArray<UObject*> UMCPythonHelper::GetAllEditedAssets()
{
    if (!GEditor) return {};
    return GEditor->GetEditorSubsystem<UAssetEditorSubsystem>()->GetAllEditedAssets();
}

TArray<UObject*> UMCPythonHelper::GetSelectedBlueprintNodes()
{
    TArray<UObject*> Result;
    if (!GEditor) return Result;
    auto* Subsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
    for (UObject* Asset : Subsystem->GetAllEditedAssets())
    {
        IAssetEditorInstance* AssetEditorInstance = Subsystem->FindEditorForAsset(Asset, false);
        FAssetEditorToolkit* AssetEditorToolkit = static_cast<FAssetEditorToolkit*>(AssetEditorInstance);
        if (!AssetEditorToolkit) continue;
        TSharedPtr<FTabManager> TabManager = AssetEditorToolkit->GetTabManager();
        if (!TabManager.IsValid()) continue;
        TSharedPtr<SDockTab> Tab = TabManager->GetOwnerTab();
        if (Tab.IsValid() && Tab->IsForeground())
        {
            FBlueprintEditor* BlueprintEditor = static_cast<FBlueprintEditor*>(AssetEditorToolkit);
            if (BlueprintEditor)
            {
                FGraphPanelSelectionSet SelectedNodes = BlueprintEditor->GetSelectedNodes();
                for (UObject* Node : SelectedNodes)
                {
                    Result.Add(Node);
                }
            }
        }
    }
    return Result;
}

TArray<FMCPythonBlueprintNodeInfo> UMCPythonHelper::GetSelectedBlueprintNodeInfos()
{
    TArray<FMCPythonBlueprintNodeInfo> Result;
    if (!GEditor) return Result;
    auto* Subsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
    for (UObject* Asset : Subsystem->GetAllEditedAssets())
    {
        IAssetEditorInstance* AssetEditorInstance = Subsystem->FindEditorForAsset(Asset, false);
        FAssetEditorToolkit* AssetEditorToolkit = static_cast<FAssetEditorToolkit*>(AssetEditorInstance);
        if (!AssetEditorToolkit) continue;
        TSharedPtr<FTabManager> TabManager = AssetEditorToolkit->GetTabManager();
        if (!TabManager.IsValid()) continue;
        TSharedPtr<SDockTab> Tab = TabManager->GetOwnerTab();
        if (Tab.IsValid() && Tab->IsForeground())
        {
            FBlueprintEditor* BlueprintEditor = static_cast<FBlueprintEditor*>(AssetEditorToolkit);
            if (BlueprintEditor)
            {
                FGraphPanelSelectionSet SelectedNodes = BlueprintEditor->GetSelectedNodes();
                for (UObject* NodeObj : SelectedNodes)
                {
                    UEdGraphNode* Node = Cast<UEdGraphNode>(NodeObj);
                    if (!Node) continue;
                    FMCPythonBlueprintNodeInfo NodeInfo;
                    NodeInfo.NodeName = Node->GetName();
                    NodeInfo.NodeTitle = Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString();
                    NodeInfo.NodeComment = Node->NodeComment;
                    for (UEdGraphPin* Pin : Node->Pins)
                    {
                        if (!Pin || Pin->bHidden) continue;
                        FMCPythonBlueprintPinInfo PinInfo;
                        FString Friendly = Pin->PinFriendlyName.ToString();
                        PinInfo.PinName = Pin->GetName();
                        PinInfo.FriendlyName = Friendly;
                        PinInfo.Direction = (Pin->Direction == EGPD_Input) ? TEXT("In") : TEXT("Out");
                        PinInfo.PinType = Pin->PinType.PinCategory.ToString();
                        if (Pin->PinType.PinSubCategoryObject.IsValid())
                        {
                            PinInfo.PinSubType = Pin->PinType.PinSubCategoryObject->GetName();
                        }
                        PinInfo.DefaultValue = Pin->DefaultValue;
                        for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
                        {
                            if (LinkedPin && LinkedPin->GetOwningNode())
                            {
                                FMCPythonPinLinkInfo LinkInfo;
                                LinkInfo.NodeName = LinkedPin->GetOwningNode()->GetName();
                                LinkInfo.NodeTitle = LinkedPin->GetOwningNode()->GetNodeTitle(ENodeTitleType::FullTitle).ToString();
                                FString LinkedFriendly = LinkedPin->PinFriendlyName.ToString();
                                LinkInfo.PinName = LinkedFriendly.IsEmpty() ? LinkedPin->GetName() : LinkedFriendly;
                                PinInfo.LinkedTo.Add(LinkInfo);
                            }
                        }
                        NodeInfo.Pins.Add(PinInfo);
                    }
                    Result.Add(NodeInfo);
                }
            }
        }
    }
    return Result;
}

// ─── Blueprint Graph Helpers (internal) ──────────────────────────────────────

// ─── GetBlueprintGraphInfo ───────────────────────────────────────────────────

FString UMCPythonHelper::GetBlueprintGraphInfo(UBlueprint* Blueprint, const FString& GraphName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found in Blueprint."), *GraphName));

    TArray<TSharedPtr<FJsonValue>> NodesArr;
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (!Node) continue;

        TSharedPtr<FJsonObject> NodeObj = MakeShareable(new FJsonObject());
        NodeObj->SetStringField(TEXT("node_name"), Node->GetName());
        NodeObj->SetStringField(TEXT("node_title"), Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
        NodeObj->SetStringField(TEXT("node_class"), Node->GetClass()->GetName());
        if (!Node->NodeComment.IsEmpty())
            NodeObj->SetStringField(TEXT("comment"), Node->NodeComment);
        NodeObj->SetNumberField(TEXT("pos_x"), Node->NodePosX);
        NodeObj->SetNumberField(TEXT("pos_y"), Node->NodePosY);

        TArray<TSharedPtr<FJsonValue>> PinsArr;
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (!Pin || Pin->bHidden) continue;
            TSharedPtr<FJsonObject> PinObj = MakeShareable(new FJsonObject());
            PinObj->SetStringField(TEXT("pin_name"), Pin->GetName());
            FString Friendly = Pin->PinFriendlyName.ToString();
            if (!Friendly.IsEmpty())
                PinObj->SetStringField(TEXT("friendly_name"), Friendly);
            PinObj->SetStringField(TEXT("direction"), (Pin->Direction == EGPD_Input) ? TEXT("Input") : TEXT("Output"));
            PinObj->SetStringField(TEXT("type"), Pin->PinType.PinCategory.ToString());
            if (Pin->PinType.PinSubCategoryObject.IsValid())
                PinObj->SetStringField(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName());
            if (!Pin->DefaultValue.IsEmpty())
                PinObj->SetStringField(TEXT("default_value"), Pin->DefaultValue);
            if (Pin->DefaultObject)
                PinObj->SetStringField(TEXT("default_object"), Pin->DefaultObject->GetPathName());

            // Linked pins
            if (Pin->LinkedTo.Num() > 0)
            {
                TArray<TSharedPtr<FJsonValue>> LinksArr;
                for (UEdGraphPin* Linked : Pin->LinkedTo)
                {
                    if (!Linked || !Linked->GetOwningNode()) continue;
                    TSharedPtr<FJsonObject> LinkObj = MakeShareable(new FJsonObject());
                    LinkObj->SetStringField(TEXT("node_name"), Linked->GetOwningNode()->GetName());
                    LinkObj->SetStringField(TEXT("pin_name"), Linked->GetName());
                    LinksArr.Add(MakeShareable(new FJsonValueObject(LinkObj)));
                }
                PinObj->SetArrayField(TEXT("linked_to"), LinksArr);
            }
            PinsArr.Add(MakeShareable(new FJsonValueObject(PinObj)));
        }
        NodeObj->SetArrayField(TEXT("pins"), PinsArr);
        NodesArr.Add(MakeShareable(new FJsonValueObject(NodeObj)));
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("graph_name"), GraphName);
    Result->SetNumberField(TEXT("node_count"), Graph->Nodes.Num());
    Result->SetArrayField(TEXT("nodes"), NodesArr);
    return SerializeJsonObj(Result);
}

// ─── ListCallableFunctions ───────────────────────────────────────────────────

FString UMCPythonHelper::ListCallableFunctions(UBlueprint* Blueprint, const FString& Filter)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UClass* GenClass = Blueprint->GeneratedClass;
    if (!GenClass)
        return MakeJsonError(TEXT("Blueprint has no generated class. Compile it first."));

    TArray<TSharedPtr<FJsonValue>> FuncsArr;
    FString FilterLower = Filter.ToLower();

    // Collect from the generated class and all parent classes
    for (UClass* Cls = GenClass; Cls; Cls = Cls->GetSuperClass())
    {
        for (TFieldIterator<UFunction> FuncIt(Cls, EFieldIteratorFlags::ExcludeSuper); FuncIt; ++FuncIt)
        {
            UFunction* Func = *FuncIt;
            if (!Func || !Func->HasAnyFunctionFlags(FUNC_BlueprintCallable))
                continue;

            FString FuncName = Func->GetName();
            FString ClassName = Cls->GetName();

            if (!FilterLower.IsEmpty())
            {
                if (!FuncName.ToLower().Contains(FilterLower) && !ClassName.ToLower().Contains(FilterLower))
                    continue;
            }

            TSharedPtr<FJsonObject> FuncObj = MakeShareable(new FJsonObject());
            FuncObj->SetStringField(TEXT("function_name"), FuncName);
            FuncObj->SetStringField(TEXT("class_name"), ClassName);
            FuncObj->SetBoolField(TEXT("is_pure"), Func->HasAnyFunctionFlags(FUNC_BlueprintPure));
            FuncObj->SetBoolField(TEXT("is_static"), Func->HasAnyFunctionFlags(FUNC_Static));

            // Parameters
            TArray<TSharedPtr<FJsonValue>> ParamsArr;
            for (TFieldIterator<FProperty> PropIt(Func); PropIt; ++PropIt)
            {
                FProperty* Prop = *PropIt;
                TSharedPtr<FJsonObject> ParamObj = MakeShareable(new FJsonObject());
                ParamObj->SetStringField(TEXT("name"), Prop->GetName());
                ParamObj->SetStringField(TEXT("type"), Prop->GetCPPType());
                ParamObj->SetBoolField(TEXT("is_return"), Prop->HasAnyPropertyFlags(CPF_ReturnParm));
                ParamObj->SetBoolField(TEXT("is_output"), Prop->HasAnyPropertyFlags(CPF_OutParm));
                ParamsArr.Add(MakeShareable(new FJsonValueObject(ParamObj)));
            }
            FuncObj->SetArrayField(TEXT("parameters"), ParamsArr);
            FuncsArr.Add(MakeShareable(new FJsonValueObject(FuncObj)));
        }
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetNumberField(TEXT("count"), FuncsArr.Num());
    Result->SetArrayField(TEXT("functions"), FuncsArr);
    return SerializeJsonObj(Result);
}

// ─── ListBlueprintVariables ──────────────────────────────────────────────────

FString UMCPythonHelper::ListBlueprintVariables(UBlueprint* Blueprint)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    TArray<TSharedPtr<FJsonValue>> VarsArr;
    for (const FBPVariableDescription& Var : Blueprint->NewVariables)
    {
        TSharedPtr<FJsonObject> VarObj = MakeShareable(new FJsonObject());
        VarObj->SetStringField(TEXT("name"), Var.VarName.ToString());
        VarObj->SetStringField(TEXT("type"), Var.VarType.PinCategory.ToString());
        if (Var.VarType.PinSubCategoryObject.IsValid())
            VarObj->SetStringField(TEXT("sub_type"), Var.VarType.PinSubCategoryObject->GetName());
        VarObj->SetBoolField(TEXT("is_array"), Var.VarType.IsArray());
        VarObj->SetBoolField(TEXT("is_set"), Var.VarType.IsSet());
        VarObj->SetBoolField(TEXT("is_map"), Var.VarType.IsMap());
        if (!Var.DefaultValue.IsEmpty())
            VarObj->SetStringField(TEXT("default_value"), Var.DefaultValue);
        VarsArr.Add(MakeShareable(new FJsonValueObject(VarObj)));
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetNumberField(TEXT("count"), VarsArr.Num());
    Result->SetArrayField(TEXT("variables"), VarsArr);
    return SerializeJsonObj(Result);
}

// ─── Blueprint Node Creation Helpers ─────────────────────────────────────────

static UEdGraphNode* CreateBPNodeFromJson(UEdGraph* Graph, UBlueprint* Blueprint, const TSharedPtr<FJsonObject>& NodeJson, FString& OutError)
{
    FString NodeType;
    if (!NodeJson->TryGetStringField(TEXT("type"), NodeType))
    {
        OutError = TEXT("Node JSON missing 'type' field.");
        return nullptr;
    }

    double PosXd = 0, PosYd = 0;
    NodeJson->TryGetNumberField(TEXT("pos_x"), PosXd);
    NodeJson->TryGetNumberField(TEXT("pos_y"), PosYd);
    int32 PosX = (int32)PosXd;
    int32 PosY = (int32)PosYd;

    UEdGraphNode* NewNode = nullptr;

    if (NodeType == TEXT("CallFunction"))
    {
        FString TargetClass, FunctionName;
        if (!NodeJson->TryGetStringField(TEXT("function_name"), FunctionName))
        {
            OutError = TEXT("CallFunction node missing 'function_name'.");
            return nullptr;
        }
        NodeJson->TryGetStringField(TEXT("target"), TargetClass);

        // Find the UFunction
        UFunction* TargetFunc = nullptr;
        if (!TargetClass.IsEmpty())
        {
            UClass* Cls = FindObject<UClass>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *TargetClass));
            if (!Cls)
                Cls = FindFirstObject<UClass>(*TargetClass, EFindFirstObjectOptions::NativeFirst);
            if (Cls)
                TargetFunc = Cls->FindFunctionByName(FName(*FunctionName));
        }

        if (!TargetFunc)
        {
            // Search in the Blueprint's generated class hierarchy
            for (UClass* Cls = Blueprint->GeneratedClass; Cls && !TargetFunc; Cls = Cls->GetSuperClass())
            {
                TargetFunc = Cls->FindFunctionByName(FName(*FunctionName));
            }
        }

        if (!TargetFunc)
        {
            OutError = FString::Printf(TEXT("Function '%s' not found (target: '%s')."), *FunctionName, *TargetClass);
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_CallFunction> Creator(*Graph);
        UK2Node_CallFunction* FuncNode = Creator.CreateNode(false);
        FuncNode->SetFromFunction(TargetFunc);
        FuncNode->NodePosX = PosX;
        FuncNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = FuncNode;
    }
    else if (NodeType == TEXT("Event"))
    {
        FString EventName;
        if (!NodeJson->TryGetStringField(TEXT("event_name"), EventName))
        {
            OutError = TEXT("Event node missing 'event_name'.");
            return nullptr;
        }

        UClass* EventClass = Blueprint->GeneratedClass ? Blueprint->GeneratedClass : Blueprint->ParentClass;
        UFunction* EventFunc = EventClass ? EventClass->FindFunctionByName(FName(*EventName)) : nullptr;

        if (!EventFunc)
        {
            OutError = FString::Printf(TEXT("Event function '%s' not found in class hierarchy."), *EventName);
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_Event> Creator(*Graph);
        UK2Node_Event* EventNode = Creator.CreateNode(false);
        EventNode->EventReference.SetExternalMember(FName(*EventName), EventClass);
        EventNode->bOverrideFunction = true;
        EventNode->NodePosX = PosX;
        EventNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = EventNode;
    }
    else if (NodeType == TEXT("CustomEvent"))
    {
        FString EventName;
        if (!NodeJson->TryGetStringField(TEXT("event_name"), EventName))
        {
            OutError = TEXT("CustomEvent node missing 'event_name'.");
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_CustomEvent> Creator(*Graph);
        UK2Node_CustomEvent* CustomNode = Creator.CreateNode(false);
        if (!CustomNode)
        {
            OutError = FString::Printf(TEXT("Failed to create CustomEvent '%s'."), *EventName);
            return nullptr;
        }
        CustomNode->CustomFunctionName = FName(*EventName);
        CustomNode->NodePosX = PosX;
        CustomNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = CustomNode;
    }
    else if (NodeType == TEXT("CastTo"))
    {
        FString CastClass;
        if (!NodeJson->TryGetStringField(TEXT("cast_class"), CastClass))
        {
            OutError = TEXT("CastTo node missing 'cast_class'.");
            return nullptr;
        }
        // Try full path first, then common module prefixes
        UClass* TargetClass = LoadClass<UObject>(nullptr, *CastClass);
        if (!TargetClass)
            TargetClass = LoadClass<UObject>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *CastClass));
        if (!TargetClass)
            TargetClass = LoadClass<UObject>(nullptr, *FString::Printf(TEXT("/Script/AIModule.%s"), *CastClass));
        if (!TargetClass)
        {
            OutError = FString::Printf(TEXT("CastTo: class '%s' not found."), *CastClass);
            return nullptr;
        }
        FGraphNodeCreator<UK2Node_DynamicCast> Creator(*Graph);
        UK2Node_DynamicCast* CastNode = Creator.CreateNode(false);
        CastNode->TargetType = TargetClass;
        CastNode->NodePosX = PosX;
        CastNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = CastNode;
    }
    else if (NodeType == TEXT("Branch"))
    {
        FGraphNodeCreator<UK2Node_IfThenElse> Creator(*Graph);
        UK2Node_IfThenElse* BranchNode = Creator.CreateNode(false);
        BranchNode->NodePosX = PosX;
        BranchNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = BranchNode;
    }
    else if (NodeType == TEXT("Sequence"))
    {
        FGraphNodeCreator<UK2Node_ExecutionSequence> Creator(*Graph);
        UK2Node_ExecutionSequence* SeqNode = Creator.CreateNode(false);
        SeqNode->NodePosX = PosX;
        SeqNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = SeqNode;
    }
    else if (NodeType == TEXT("VariableGet"))
    {
        FString VarName;
        if (!NodeJson->TryGetStringField(TEXT("variable_name"), VarName))
        {
            OutError = TEXT("VariableGet node missing 'variable_name'.");
            return nullptr;
        }

        FString VarClass;
        const bool bHasExternalClass = NodeJson->TryGetStringField(TEXT("variable_class"), VarClass) && !VarClass.IsEmpty();

        FGraphNodeCreator<UK2Node_VariableGet> Creator(*Graph);
        UK2Node_VariableGet* GetNode = Creator.CreateNode(false);

        if (bHasExternalClass)
        {
            UClass* OwnerClass = LoadClass<UObject>(nullptr, *VarClass);
            if (!OwnerClass)
                OwnerClass = LoadClass<UObject>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *VarClass));
            if (OwnerClass)
                GetNode->VariableReference.SetExternalMember(FName(*VarName), OwnerClass);
            else
                GetNode->VariableReference.SetSelfMember(FName(*VarName));
        }
        else
        {
            GetNode->VariableReference.SetSelfMember(FName(*VarName));
        }

        GetNode->NodePosX = PosX;
        GetNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = GetNode;
    }
    else if (NodeType == TEXT("VariableSet"))
    {
        FString VarName;
        if (!NodeJson->TryGetStringField(TEXT("variable_name"), VarName))
        {
            OutError = TEXT("VariableSet node missing 'variable_name'.");
            return nullptr;
        }

        FString VarClass;
        const bool bHasExternalClass = NodeJson->TryGetStringField(TEXT("variable_class"), VarClass) && !VarClass.IsEmpty();

        FGraphNodeCreator<UK2Node_VariableSet> Creator(*Graph);
        UK2Node_VariableSet* SetNode = Creator.CreateNode(false);

        if (bHasExternalClass)
        {
            UClass* OwnerClass = LoadClass<UObject>(nullptr, *VarClass);
            if (!OwnerClass)
                OwnerClass = LoadClass<UObject>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *VarClass));
            if (OwnerClass)
                SetNode->VariableReference.SetExternalMember(FName(*VarName), OwnerClass);
            else
                SetNode->VariableReference.SetSelfMember(FName(*VarName));
        }
        else
        {
            SetNode->VariableReference.SetSelfMember(FName(*VarName));
        }

        SetNode->NodePosX = PosX;
        SetNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = SetNode;
    }
    else if (NodeType == TEXT("MacroInstance"))
    {
        FString MacroName;
        if (!NodeJson->TryGetStringField(TEXT("macro_name"), MacroName))
        {
            OutError = TEXT("MacroInstance node missing 'macro_name'.");
            return nullptr;
        }

        // Search for macro graph in the Blueprint and its parents
        UEdGraph* MacroGraph = nullptr;
        for (UBlueprint* SearchBP = Blueprint; SearchBP && !MacroGraph; SearchBP = Cast<UBlueprint>(SearchBP->ParentClass->ClassGeneratedBy))
        {
            for (UEdGraph* MGraph : SearchBP->MacroGraphs)
            {
                if (MGraph && MGraph->GetName() == MacroName)
                {
                    MacroGraph = MGraph;
                    break;
                }
            }
            if (!SearchBP->ParentClass || !SearchBP->ParentClass->ClassGeneratedBy)
                break;
        }

        // Also search engine-level macros (e.g., ForEachLoop)
        if (!MacroGraph)
        {
            UBlueprint* MacroLibBP = LoadObject<UBlueprint>(nullptr, TEXT("/Engine/EditorBlueprintResources/StandardMacros.StandardMacros"));
            if (MacroLibBP)
            {
                for (UEdGraph* MGraph : MacroLibBP->MacroGraphs)
                {
                    if (MGraph && MGraph->GetName() == MacroName)
                    {
                        MacroGraph = MGraph;
                        break;
                    }
                }
            }
        }

        if (!MacroGraph)
        {
            OutError = FString::Printf(TEXT("Macro '%s' not found."), *MacroName);
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_MacroInstance> Creator(*Graph);
        UK2Node_MacroInstance* MacroNode = Creator.CreateNode(false);
        MacroNode->SetMacroGraph(MacroGraph);
        MacroNode->NodePosX = PosX;
        MacroNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = MacroNode;
    }
    else if (NodeType == TEXT("InputKey"))
    {
        FString KeyName;
        if (!NodeJson->TryGetStringField(TEXT("key_name"), KeyName))
        {
            OutError = TEXT("InputKey node missing 'key_name'.");
            return nullptr;
        }
        FGraphNodeCreator<UK2Node_InputKey> Creator(*Graph);
        UK2Node_InputKey* KeyNode = Creator.CreateNode(false);
        KeyNode->InputKey = FKey(*KeyName);
        KeyNode->NodePosX = PosX;
        KeyNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = KeyNode;
    }
    else if (NodeType == TEXT("SpawnActor"))
    {
        FGraphNodeCreator<UK2Node_SpawnActorFromClass> Creator(*Graph);
        UK2Node_SpawnActorFromClass* SpawnNode = Creator.CreateNode(false);
        SpawnNode->NodePosX = PosX;
        SpawnNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = SpawnNode;
    }
    else
    {
        OutError = FString::Printf(TEXT("Unknown node type '%s'. Supported: CallFunction, Event, CustomEvent, CastTo, Branch, Sequence, VariableGet, VariableSet, MacroInstance, InputKey, SpawnActor."), *NodeType);
        return nullptr;
    }

    // Set pin defaults if specified
    if (NewNode && NodeJson->HasField(TEXT("pin_defaults")))
    {
        const TSharedPtr<FJsonObject>& PinDefaults = NodeJson->GetObjectField(TEXT("pin_defaults"));
        for (auto& Pair : PinDefaults->Values)
        {
            // *Pair.Key yields const TCHAR* on both UE 5.7 (FString key) and 5.8 (UE::FSharedString key).
            UEdGraphPin* Pin = FindPinByName(NewNode, FString(*Pair.Key), EGPD_Input);
            if (Pin)
            {
                FString Value;
                if (Pair.Value->TryGetString(Value))
                {
                    Pin->DefaultValue = Value;
                }
            }
        }
    }

    return NewNode;
}

// ─── AddBlueprintNode UFUNCTION ──────────────────────────────────────────────

FString UMCPythonHelper::AddBlueprintNode(UBlueprint* Blueprint, const FString& GraphName, const FString& NodeJson)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(NodeJson);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
        return MakeJsonError(TEXT("Failed to parse NodeJson."));

    FString Error;
    UEdGraphNode* NewNode = CreateBPNodeFromJson(Graph, Blueprint, JsonObj, Error);
    if (!NewNode)
        return MakeJsonError(Error);

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("node_name"), NewNode->GetName());
    Result->SetStringField(TEXT("node_title"), NewNode->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
    Result->SetStringField(TEXT("message"), FString::Printf(TEXT("Node '%s' added to graph '%s'."), *NewNode->GetNodeTitle(ENodeTitleType::FullTitle).ToString(), *GraphName));

    // Return pin info so caller knows how to connect
    TArray<TSharedPtr<FJsonValue>> PinsArr;
    for (UEdGraphPin* Pin : NewNode->Pins)
    {
        if (!Pin || Pin->bHidden) continue;
        TSharedPtr<FJsonObject> PinObj = MakeShareable(new FJsonObject());
        PinObj->SetStringField(TEXT("pin_name"), Pin->GetName());
        FString Friendly = Pin->PinFriendlyName.ToString();
        if (!Friendly.IsEmpty())
            PinObj->SetStringField(TEXT("friendly_name"), Friendly);
        PinObj->SetStringField(TEXT("direction"), (Pin->Direction == EGPD_Input) ? TEXT("Input") : TEXT("Output"));
        PinObj->SetStringField(TEXT("type"), Pin->PinType.PinCategory.ToString());
        PinsArr.Add(MakeShareable(new FJsonValueObject(PinObj)));
    }
    Result->SetArrayField(TEXT("pins"), PinsArr);
    return SerializeJsonObj(Result);
}

// ─── ConnectBlueprintPins UFUNCTION ──────────────────────────────────────────

FString UMCPythonHelper::ConnectBlueprintPins(UBlueprint* Blueprint, const FString& GraphName,
    const FString& SourceNodeName, const FString& SourcePinName,
    const FString& TargetNodeName, const FString& TargetPinName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    UEdGraphNode* SourceNode = FindBPNodeByName(Graph, SourceNodeName);
    if (!SourceNode)
        return MakeJsonError(FString::Printf(TEXT("Source node '%s' not found."), *SourceNodeName));

    UEdGraphNode* TargetNode = FindBPNodeByName(Graph, TargetNodeName);
    if (!TargetNode)
        return MakeJsonError(FString::Printf(TEXT("Target node '%s' not found."), *TargetNodeName));

    UEdGraphPin* SourcePin = FindPinByName(SourceNode, SourcePinName);
    if (!SourcePin)
    {
        TArray<FString> PinNames;
        for (UEdGraphPin* P : SourceNode->Pins) { if (P && !P->bHidden) PinNames.Add(P->GetName()); }
        return MakeJsonError(FString::Printf(TEXT("Pin '%s' not found on node '%s'. Available: %s"),
            *SourcePinName, *SourceNodeName, *FString::Join(PinNames, TEXT(", "))));
    }

    UEdGraphPin* TargetPin = FindPinByName(TargetNode, TargetPinName);
    if (!TargetPin)
    {
        TArray<FString> PinNames;
        for (UEdGraphPin* P : TargetNode->Pins) { if (P && !P->bHidden) PinNames.Add(P->GetName()); }
        return MakeJsonError(FString::Printf(TEXT("Pin '%s' not found on node '%s'. Available: %s"),
            *TargetPinName, *TargetNodeName, *FString::Join(PinNames, TEXT(", "))));
    }

    // Verify directions are compatible (output -> input)
    if (SourcePin->Direction == TargetPin->Direction)
        return MakeJsonError(FString::Printf(TEXT("Cannot connect pins with same direction (%s)."),
            SourcePin->Direction == EGPD_Input ? TEXT("both Input") : TEXT("both Output")));

    // Check if connection is allowed by the schema and handle BREAK_OTHERS
    const UEdGraphSchema* Schema = Graph->GetSchema();
    if (Schema)
    {
        FPinConnectionResponse Response = Schema->CanCreateConnection(SourcePin, TargetPin);
        if (Response.Response == CONNECT_RESPONSE_DISALLOW)
            return MakeJsonError(FString::Printf(TEXT("Connection not allowed: %s"), *Response.Message.ToString()));
        // Break existing connections when schema requires it (e.g. exec output already connected)
        if (Response.Response == CONNECT_RESPONSE_BREAK_OTHERS_A)
            SourcePin->BreakAllPinLinks();
        else if (Response.Response == CONNECT_RESPONSE_BREAK_OTHERS_B)
            TargetPin->BreakAllPinLinks();
    }

    SourcePin->MakeLinkTo(TargetPin);

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    return MakeJsonSuccess(FString::Printf(TEXT("Connected %s.%s -> %s.%s"),
        *SourceNodeName, *SourcePinName, *TargetNodeName, *TargetPinName));
}

// ─── RemoveBlueprintNode UFUNCTION ───────────────────────────────────────────

FString UMCPythonHelper::RemoveBlueprintNode(UBlueprint* Blueprint, const FString& GraphName,
    const FString& NodeName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    UEdGraphNode* Node = FindBPNodeByName(Graph, NodeName);
    if (!Node)
        return MakeJsonError(FString::Printf(TEXT("Node '%s' not found in graph '%s'."), *NodeName, *GraphName));

    // Break all pin connections first
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin)
            Pin->BreakAllPinLinks();
    }

    Graph->RemoveNode(Node);
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    return MakeJsonSuccess(FString::Printf(TEXT("Node '%s' removed from graph '%s'."), *NodeName, *GraphName));
}

// ─── BuildBlueprintGraph UFUNCTION ───────────────────────────────────────────

static void LayoutBPGraphNodes(const TMap<FString, UEdGraphNode*>& NodeMap,
    const TArray<TSharedPtr<FJsonValue>>& Connections)
{
    // Simple left-to-right layout based on execution flow
    // Assign columns based on connection depth
    TMap<FString, int32> NodeColumns;
    TSet<FString> Visited;

    // Find nodes with no incoming exec connections (roots)
    TSet<FString> HasIncoming;
    for (auto& ConnVal : Connections)
    {
        const TSharedPtr<FJsonObject>& Conn = ConnVal->AsObject();
        if (!Conn.IsValid()) continue;
        FString TargetNodeId;
        if (Conn->TryGetStringField(TEXT("target_node"), TargetNodeId))
            HasIncoming.Add(TargetNodeId);
    }

    // Assign column 0 to roots, then propagate
    int32 Col = 0;
    for (auto& Pair : NodeMap)
    {
        if (!HasIncoming.Contains(Pair.Key))
            NodeColumns.Add(Pair.Key, 0);
    }

    // Propagate columns through connections
    for (auto& ConnVal : Connections)
    {
        const TSharedPtr<FJsonObject>& Conn = ConnVal->AsObject();
        if (!Conn.IsValid()) continue;
        FString SourceId, TargetId;
        Conn->TryGetStringField(TEXT("source_node"), SourceId);
        Conn->TryGetStringField(TEXT("target_node"), TargetId);

        int32* SourceCol = NodeColumns.Find(SourceId);
        int32 SC = SourceCol ? *SourceCol : 0;
        int32* TargetCol = NodeColumns.Find(TargetId);
        if (!TargetCol || *TargetCol <= SC)
            NodeColumns.Add(TargetId, SC + 1);
    }

    // Count nodes per column for Y positioning
    TMap<int32, int32> ColumnRowCount;
    const float XStep = 400.0f;
    const float YStep = 200.0f;

    for (auto& Pair : NodeMap)
    {
        int32* ColPtr = NodeColumns.Find(Pair.Key);
        int32 C = ColPtr ? *ColPtr : 0;
        int32* RowPtr = ColumnRowCount.Find(C);
        int32 Row = RowPtr ? *RowPtr : 0;

        Pair.Value->NodePosX = (int32)(C * XStep);
        Pair.Value->NodePosY = (int32)(Row * YStep);

        ColumnRowCount.Add(C, Row + 1);
    }
}

FString UMCPythonHelper::BuildBlueprintGraph(UBlueprint* Blueprint, const FString& GraphName,
    const FString& GraphJson)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    // Parse JSON
    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(GraphJson);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
        return MakeJsonError(TEXT("Failed to parse GraphJson."));

    if (!JsonObj->HasField(TEXT("nodes")))
        return MakeJsonError(TEXT("GraphJson missing 'nodes' array."));

    const TArray<TSharedPtr<FJsonValue>>& NodesArr = JsonObj->GetArrayField(TEXT("nodes"));
    TArray<TSharedPtr<FJsonValue>> ConnectionsArr;
    if (JsonObj->HasField(TEXT("connections")))
        ConnectionsArr = JsonObj->GetArrayField(TEXT("connections"));

    // Remove existing user-created nodes (keep root/entry nodes)
    TArray<UEdGraphNode*> NodesToRemove;
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (!Node) continue;
        // Keep entry points (function entry, etc.) but remove user nodes
        // For EventGraph, we typically remove all non-essential nodes
        if (!Node->IsA<UK2Node_Event>())
        {
            NodesToRemove.Add(Node);
        }
    }
    for (UEdGraphNode* Node : NodesToRemove)
    {
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (Pin) Pin->BreakAllPinLinks();
        }
        Graph->RemoveNode(Node);
    }

    // Create nodes from JSON
    TMap<FString, UEdGraphNode*> NodeMap; // id -> node
    TArray<FString> CreationErrors;

    for (auto& NodeVal : NodesArr)
    {
        const TSharedPtr<FJsonObject>& NodeObj = NodeVal->AsObject();
        if (!NodeObj.IsValid()) continue;

        FString NodeId;
        if (!NodeObj->TryGetStringField(TEXT("id"), NodeId))
        {
            CreationErrors.Add(TEXT("Node missing 'id' field."));
            continue;
        }

        FString Error;
        UEdGraphNode* NewNode = CreateBPNodeFromJson(Graph, Blueprint, NodeObj, Error);
        if (NewNode)
        {
            NodeMap.Add(NodeId, NewNode);
        }
        else
        {
            CreationErrors.Add(FString::Printf(TEXT("Node '%s': %s"), *NodeId, *Error));
        }
    }

    // Connect pins
    TArray<FString> ConnectionErrors;
    for (auto& ConnVal : ConnectionsArr)
    {
        const TSharedPtr<FJsonObject>& ConnObj = ConnVal->AsObject();
        if (!ConnObj.IsValid()) continue;

        FString SourceNodeId, SourcePinName, TargetNodeId, TargetPinName;
        ConnObj->TryGetStringField(TEXT("source_node"), SourceNodeId);
        ConnObj->TryGetStringField(TEXT("source_pin"), SourcePinName);
        ConnObj->TryGetStringField(TEXT("target_node"), TargetNodeId);
        ConnObj->TryGetStringField(TEXT("target_pin"), TargetPinName);

        UEdGraphNode** SourceNodePtr = NodeMap.Find(SourceNodeId);
        UEdGraphNode** TargetNodePtr = NodeMap.Find(TargetNodeId);

        if (!SourceNodePtr || !*SourceNodePtr)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Source node '%s' not found."), *SourceNodeId));
            continue;
        }
        if (!TargetNodePtr || !*TargetNodePtr)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Target node '%s' not found."), *TargetNodeId));
            continue;
        }

        UEdGraphPin* SourcePin = FindPinByName(*SourceNodePtr, SourcePinName);
        UEdGraphPin* TargetPin = FindPinByName(*TargetNodePtr, TargetPinName);

        if (!SourcePin)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Pin '%s' not found on '%s'."), *SourcePinName, *SourceNodeId));
            continue;
        }
        if (!TargetPin)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Pin '%s' not found on '%s'."), *TargetPinName, *TargetNodeId));
            continue;
        }

        SourcePin->MakeLinkTo(TargetPin);
    }

    // Layout nodes
    LayoutBPGraphNodes(NodeMap, ConnectionsArr);

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    // Build result
    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), CreationErrors.Num() == 0 && ConnectionErrors.Num() == 0);
    Result->SetNumberField(TEXT("nodes_created"), NodeMap.Num());
    Result->SetNumberField(TEXT("connections_made"), ConnectionsArr.Num() - ConnectionErrors.Num());

    FString Message = FString::Printf(TEXT("Built graph '%s': %d nodes, %d connections."),
        *GraphName, NodeMap.Num(), ConnectionsArr.Num() - ConnectionErrors.Num());
    if (CreationErrors.Num() > 0 || ConnectionErrors.Num() > 0)
        Message += TEXT(" Some errors occurred.");
    Result->SetStringField(TEXT("message"), Message);

    if (CreationErrors.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> ErrArr;
        for (const FString& Err : CreationErrors)
            ErrArr.Add(MakeShareable(new FJsonValueString(Err)));
        Result->SetArrayField(TEXT("creation_errors"), ErrArr);
    }
    if (ConnectionErrors.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> ErrArr;
        for (const FString& Err : ConnectionErrors)
            ErrArr.Add(MakeShareable(new FJsonValueString(Err)));
        Result->SetArrayField(TEXT("connection_errors"), ErrArr);
    }

    // Return node_id -> node_name mapping for reference
    TSharedPtr<FJsonObject> MapObj = MakeShareable(new FJsonObject());
    for (auto& Pair : NodeMap)
    {
        MapObj->SetStringField(Pair.Key, Pair.Value->GetName());
    }
    Result->SetObjectField(TEXT("node_id_to_name"), MapObj);

    return SerializeJsonObj(Result);
}

// ─── CompileBlueprint UFUNCTION ──────────────────────────────────────────────

FString UMCPythonHelper::CompileBlueprint(UBlueprint* Blueprint)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    FKismetEditorUtilities::CompileBlueprint(Blueprint);

    // Check compile status
    bool bHasError = (Blueprint->Status == BS_Error);
    bool bUpToDate = (Blueprint->Status == BS_UpToDate);

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), !bHasError);

    FString StatusStr;
    switch (Blueprint->Status)
    {
    case BS_UpToDate: StatusStr = TEXT("UpToDate"); break;
    case BS_Error: StatusStr = TEXT("Error"); break;
    case BS_Dirty: StatusStr = TEXT("Dirty"); break;
    case BS_BeingCreated: StatusStr = TEXT("BeingCreated"); break;
    default: StatusStr = TEXT("Unknown"); break;
    }
    Result->SetStringField(TEXT("status"), StatusStr);
    Result->SetStringField(TEXT("message"),
        bHasError ? TEXT("Blueprint compilation failed. Check the output log for details.")
                  : TEXT("Blueprint compiled successfully."));

    return SerializeJsonObj(Result);
}

// ─── SetBlueprintCDOProperty UFUNCTION ───────────────────────────────────────

FString UMCPythonHelper::SetBlueprintCDOProperty(UBlueprint* Blueprint, const FString& PropertyName, const FString& ValueStr)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Blueprint is null."));

    UClass* GenClass = Blueprint->GeneratedClass;
    if (!GenClass)
        return MakeJsonError(TEXT("Blueprint has no GeneratedClass."));

    UObject* CDO = GenClass->GetDefaultObject(false);
    if (!CDO)
        return MakeJsonError(TEXT("Could not get CDO."));

    FProperty* FoundProp = nullptr;
    for (TFieldIterator<FProperty> It(GenClass, EFieldIterationFlags::IncludeSuper); It; ++It)
    {
        if (It->GetName().Equals(PropertyName, ESearchCase::IgnoreCase))
        {
            FoundProp = *It;
            break;
        }
    }

    if (!FoundProp)
        return MakeJsonError(FString::Printf(TEXT("Property '%s' not found on '%s' or any parent class."), *PropertyName, *Blueprint->GetName()));

    void* PropAddr = FoundProp->ContainerPtrToValuePtr<void>(CDO);

    auto MarkModified = [&]()
    {
        CDO->Modify();
        Blueprint->Modify();
        FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    };

    // TSubclassOf<T>
    if (FClassProperty* ClassProp = CastField<FClassProperty>(FoundProp))
    {
        UClass* TargetClass = LoadClass<UObject>(nullptr, *ValueStr);
        if (!TargetClass)
        {
            UBlueprint* ValBP = Cast<UBlueprint>(StaticLoadObject(UBlueprint::StaticClass(), nullptr, *ValueStr));
            if (ValBP) TargetClass = ValBP->GeneratedClass;
        }
        if (!TargetClass)
            return MakeJsonError(FString::Printf(TEXT("Could not resolve class from '%s'."), *ValueStr));
        ClassProp->SetPropertyValue(PropAddr, TargetClass);
        MarkModified();
        TSharedPtr<FJsonObject> R = MakeShareable(new FJsonObject());
        R->SetBoolField(TEXT("success"), true);
        R->SetStringField(TEXT("property"), PropertyName);
        R->SetStringField(TEXT("value"), TargetClass->GetName());
        R->SetStringField(TEXT("message"), FString::Printf(TEXT("ClassProperty '%s' set to '%s'."), *PropertyName, *TargetClass->GetName()));
        return SerializeJsonObj(R);
    }

    // TSoftClassPtr<T>
    if (FSoftClassProperty* SoftClassProp = CastField<FSoftClassProperty>(FoundProp))
    {
        FSoftObjectPath SoftPath(ValueStr);
        FSoftObjectPtr SoftPtr(SoftPath);
        SoftClassProp->SetPropertyValue(PropAddr, SoftPtr);
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("SoftClassProperty '%s' set to '%s'."), *PropertyName, *ValueStr));
    }

    // UObject* refs (must come after class properties since FClassProperty extends FObjectProperty)
    if (FObjectProperty* ObjProp = CastField<FObjectProperty>(FoundProp))
    {
        UObject* LoadedObj = StaticLoadObject(ObjProp->PropertyClass, nullptr, *ValueStr);
        if (!LoadedObj)
            return MakeJsonError(FString::Printf(TEXT("Could not load object from '%s'."), *ValueStr));
        ObjProp->SetObjectPropertyValue(PropAddr, LoadedObj);
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("ObjectProperty '%s' set."), *PropertyName));
    }

    // bool
    if (FBoolProperty* BoolProp = CastField<FBoolProperty>(FoundProp))
    {
        bool bVal = (ValueStr == TEXT("true") || ValueStr == TEXT("True") || ValueStr == TEXT("1"));
        BoolProp->SetPropertyValue(PropAddr, bVal);
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("BoolProperty '%s' set to %s."), *PropertyName, bVal ? TEXT("true") : TEXT("false")));
    }

    // int / float / double
    if (FNumericProperty* NumProp = CastField<FNumericProperty>(FoundProp))
    {
        if (NumProp->IsFloatingPoint())
            NumProp->SetFloatingPointPropertyValue(PropAddr, FCString::Atod(*ValueStr));
        else
            NumProp->SetIntPropertyValue(PropAddr, (int64)FCString::Atoi64(*ValueStr));
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("NumericProperty '%s' set to '%s'."), *PropertyName, *ValueStr));
    }

    // FString
    if (FStrProperty* StrProp = CastField<FStrProperty>(FoundProp))
    {
        StrProp->SetPropertyValue(PropAddr, ValueStr);
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("StrProperty '%s' set."), *PropertyName));
    }

    // FName
    if (FNameProperty* NameProp = CastField<FNameProperty>(FoundProp))
    {
        NameProp->SetPropertyValue(PropAddr, FName(*ValueStr));
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("NameProperty '%s' set."), *PropertyName));
    }

    // FText
    if (FTextProperty* TextProp = CastField<FTextProperty>(FoundProp))
    {
        TextProp->SetPropertyValue(PropAddr, FText::FromString(ValueStr));
        MarkModified();
        return MakeJsonSuccess(FString::Printf(TEXT("TextProperty '%s' set."), *PropertyName));
    }

    return MakeJsonError(FString::Printf(TEXT("Unsupported property type '%s' for property '%s'."),
        *FoundProp->GetClass()->GetName(), *PropertyName));
}

// ─── AddComponentToBlueprint UFUNCTION ───────────────────────────────────────

FString UMCPythonHelper::AddComponentToBlueprint(UBlueprint* Blueprint,
    const FString& ComponentClassPath,
    const FString& ComponentName,
    float LocationX, float LocationY, float LocationZ,
    float RotationPitch, float RotationYaw, float RotationRoll,
    const FString& ParentComponentName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
    if (!SCS)
        return MakeJsonError(TEXT("Blueprint has no SimpleConstructionScript."));

    UClass* CompClass = LoadClass<UActorComponent>(nullptr, *ComponentClassPath);
    if (!CompClass)
        return MakeJsonError(FString::Printf(TEXT("Component class not found: %s"), *ComponentClassPath));

    USCS_Node* NewNode = SCS->CreateNode(CompClass, FName(*ComponentName));
    if (!NewNode)
        return MakeJsonError(TEXT("Failed to create SCS node."));

    if (USceneComponent* SceneComp = Cast<USceneComponent>(NewNode->ComponentTemplate))
    {
        SceneComp->SetRelativeLocation(FVector(LocationX, LocationY, LocationZ));
        SceneComp->SetRelativeRotation(FRotator(RotationPitch, RotationYaw, RotationRoll));
    }

    if (!ParentComponentName.IsEmpty())
    {
        USCS_Node* ParentNode = SCS->FindSCSNode(FName(*ParentComponentName));
        if (ParentNode)
            ParentNode->AddChildNode(NewNode);
        else
            SCS->AddNode(NewNode);
    }
    else
    {
        const TArray<USCS_Node*>& RootNodes = SCS->GetRootNodes();
        if (RootNodes.Num() > 0)
            RootNodes[0]->AddChildNode(NewNode);
        else
            SCS->AddNode(NewNode);
    }

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("node_name"), NewNode->GetVariableName().ToString());
    R->SetStringField(TEXT("component_class"), CompClass->GetName());
    R->SetStringField(TEXT("message"),
        FString::Printf(TEXT("Added '%s' (%s)."), *ComponentName, *CompClass->GetName()));
    return SerializeJsonObj(R);
}

// ─── ListBlueprintComponents UFUNCTION ───────────────────────────────────────

FString UMCPythonHelper::ListBlueprintComponents(UBlueprint* Blueprint)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
    if (!SCS)
        return MakeJsonError(TEXT("Blueprint has no SimpleConstructionScript."));

    TArray<TSharedPtr<FJsonValue>> ComponentsArr;
    for (USCS_Node* Node : SCS->GetAllNodes())
    {
        if (!Node) continue;
        TSharedPtr<FJsonObject> Obj = MakeShared<FJsonObject>();
        Obj->SetStringField(TEXT("variable_name"), Node->GetVariableName().ToString());
        if (Node->ComponentTemplate)
        {
            Obj->SetStringField(TEXT("class"), Node->ComponentTemplate->GetClass()->GetName());
            Obj->SetBoolField(TEXT("is_native"), false);
        }
        else
        {
            Obj->SetStringField(TEXT("class"), TEXT("Unknown"));
            Obj->SetBoolField(TEXT("is_native"), false);
        }
        USCS_Node* Parent = nullptr;
        for (USCS_Node* Candidate : SCS->GetAllNodes())
        {
            if (Candidate && Candidate->GetChildNodes().Contains(Node))
            {
                Parent = Candidate;
                break;
            }
        }
        Obj->SetStringField(TEXT("parent"), Parent ? Parent->GetVariableName().ToString() : TEXT(""));
        ComponentsArr.Add(MakeShareable(new FJsonValueObject(Obj)));
    }

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetArrayField(TEXT("components"), ComponentsArr);
    R->SetNumberField(TEXT("count"), ComponentsArr.Num());
    return SerializeJsonObj(R);
}

// ─── RemoveComponentFromBlueprint UFUNCTION ───────────────────────────────────

FString UMCPythonHelper::RemoveComponentFromBlueprint(UBlueprint* Blueprint, const FString& ComponentName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
    if (!SCS)
        return MakeJsonError(TEXT("Blueprint has no SimpleConstructionScript."));

    USCS_Node* Node = SCS->FindSCSNode(FName(*ComponentName));
    if (!Node)
        return MakeJsonError(FString::Printf(TEXT("Component '%s' not found in SCS."), *ComponentName));

    FString RemovedClass = Node->ComponentTemplate ? Node->ComponentTemplate->GetClass()->GetName() : TEXT("Unknown");

    SCS->RemoveNodeAndPromoteChildren(Node);
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("component_name"), ComponentName);
    R->SetStringField(TEXT("class"), RemovedClass);
    R->SetStringField(TEXT("message"), FString::Printf(TEXT("Component '%s' (%s) removed."), *ComponentName, *RemovedClass));
    return SerializeJsonObj(R);
}

// ─── SetComponentProperty UFUNCTION ──────────────────────────────────────────

FString UMCPythonHelper::SetComponentProperty(UBlueprint* Blueprint,
    const FString& ComponentName, const FString& PropertyName, const FString& Value)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
    if (!SCS)
        return MakeJsonError(TEXT("Blueprint has no SimpleConstructionScript."));

    USCS_Node* Node = SCS->FindSCSNode(FName(*ComponentName));
    if (!Node)
        return MakeJsonError(FString::Printf(TEXT("Component '%s' not found in SCS."), *ComponentName));

    UObject* Template = Node->ComponentTemplate;
    if (!Template)
        return MakeJsonError(FString::Printf(TEXT("Component '%s' has no template."), *ComponentName));

    FProperty* Prop = Template->GetClass()->FindPropertyByName(FName(*PropertyName));
    if (!Prop)
        return MakeJsonError(FString::Printf(TEXT("Property '%s' not found on component '%s'."), *PropertyName, *ComponentName));

    Template->Modify();
    void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(Template);
    const TCHAR* ImportResult = Prop->ImportText_Direct(*Value, ValueAddr, Template, PPF_None);
    if (!ImportResult)
        return MakeJsonError(FString::Printf(TEXT("Failed to set property '%s' to '%s'."), *PropertyName, *Value));

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("component"), ComponentName);
    R->SetStringField(TEXT("property"), PropertyName);
    R->SetStringField(TEXT("value"), Value);
    return SerializeJsonObj(R);
}

// ─── SetBlueprintNodePosition UFUNCTION ──────────────────────────────────────

FString UMCPythonHelper::SetBlueprintNodePosition(UBlueprint* Blueprint,
    const FString& GraphName, const FString& NodeName, float PosX, float PosY)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    UEdGraphNode* Node = FindBPNodeByName(Graph, NodeName);
    if (!Node)
        return MakeJsonError(FString::Printf(TEXT("Node '%s' not found in graph '%s'."), *NodeName, *GraphName));

    Node->Modify();
    Node->NodePosX = (int32)PosX;
    Node->NodePosY = (int32)PosY;

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("node"), NodeName);
    R->SetNumberField(TEXT("pos_x"), PosX);
    R->SetNumberField(TEXT("pos_y"), PosY);
    return SerializeJsonObj(R);
}

// ─── SetBlueprintNodePinDefault ──────────────────────────────────────────────

FString UMCPythonHelper::SetBlueprintNodePinDefault(UBlueprint* Blueprint,
    const FString& GraphName, const FString& NodeName,
    const FString& PinName, const FString& Value)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    UEdGraphNode* Node = FindBPNodeByName(Graph, NodeName);
    if (!Node)
        return MakeJsonError(FString::Printf(TEXT("Node '%s' not found."), *NodeName));

    UEdGraphPin* Pin = FindPinByName(Node, PinName, EGPD_Input);
    if (!Pin)
    {
        TArray<FString> Names;
        for (UEdGraphPin* P : Node->Pins) { if (P && !P->bHidden && P->Direction == EGPD_Input) Names.Add(P->GetName()); }
        return MakeJsonError(FString::Printf(TEXT("Input pin '%s' not found. Available: %s"), *PinName, *FString::Join(Names, TEXT(", "))));
    }

    // For object-type pins, try loading the asset
    if (Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Object ||
        Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_SoftObject ||
        Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Class ||
        Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_SoftClass)
    {
        UObject* Asset = StaticLoadObject(UObject::StaticClass(), nullptr, *Value);
        if (!Asset)
            return MakeJsonError(FString::Printf(TEXT("Could not load asset: %s"), *Value));
        Pin->DefaultObject = Asset;
        Pin->DefaultValue = TEXT("");
    }
    else
    {
        Pin->DefaultValue = Value;
    }

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("message"), FString::Printf(TEXT("Set pin '%s' on '%s' to '%s'."), *PinName, *NodeName, *Value));
    return SerializeJsonObj(R);
}


// ─── SkeletalMesh / Skeleton Helpers ──────────────────────────────────────────

FString UMCPythonHelper::GetSkeletonBones(USkeletalMesh* Mesh)
{
    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    if (!Mesh)
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), TEXT("SkeletalMesh is null."));
        return SerializeJsonObj(R);
    }

    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    TArray<TSharedPtr<FJsonValue>> Bones;
    for (int32 i = 0; i < Ref.GetNum(); ++i)
    {
        TSharedPtr<FJsonObject> B = MakeShared<FJsonObject>();
        B->SetStringField(TEXT("name"), Ref.GetBoneName(i).ToString());
        B->SetNumberField(TEXT("index"), i);
        const int32 ParentIdx = Ref.GetParentIndex(i);
        B->SetStringField(TEXT("parent"), ParentIdx >= 0 ? Ref.GetBoneName(ParentIdx).ToString() : TEXT(""));
        Bones.Add(MakeShared<FJsonValueObject>(B));
    }

    R->SetBoolField(TEXT("success"), true);
    R->SetNumberField(TEXT("bone_count"), Ref.GetNum());
    R->SetArrayField(TEXT("bones"), Bones);
    return SerializeJsonObj(R);
}

FString UMCPythonHelper::AddSkeletalMeshSocket(USkeletalMesh* Mesh, const FString& SocketName,
    const FString& BoneName,
    float LocationX, float LocationY, float LocationZ,
    float RotationPitch, float RotationYaw, float RotationRoll)
{
    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    if (!Mesh)
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), TEXT("SkeletalMesh is null."));
        return SerializeJsonObj(R);
    }
    if (SocketName.IsEmpty() || BoneName.IsEmpty())
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), TEXT("SocketName and BoneName are required."));
        return SerializeJsonObj(R);
    }
    if (Mesh->FindSocket(FName(*SocketName)) != nullptr)
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), FString::Printf(TEXT("Socket '%s' already exists."), *SocketName));
        return SerializeJsonObj(R);
    }
    if (Mesh->GetRefSkeleton().FindBoneIndex(FName(*BoneName)) == INDEX_NONE)
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), FString::Printf(TEXT("Bone '%s' not found in skeleton."), *BoneName));
        return SerializeJsonObj(R);
    }

    Mesh->Modify();
    USkeletalMeshSocket* Socket = NewObject<USkeletalMeshSocket>(Mesh);
    Socket->SocketName = FName(*SocketName);
    Socket->BoneName = FName(*BoneName);
    Socket->RelativeLocation = FVector(LocationX, LocationY, LocationZ);
    Socket->RelativeRotation = FRotator(RotationPitch, RotationYaw, RotationRoll);
    Mesh->AddSocket(Socket, false);
    Mesh->MarkPackageDirty();

    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("socket_name"), SocketName);
    R->SetStringField(TEXT("bone_name"), BoneName);
    R->SetStringField(TEXT("message"), FString::Printf(TEXT("Added socket '%s' on bone '%s'."), *SocketName, *BoneName));
    return SerializeJsonObj(R);
}

FString UMCPythonHelper::RemoveSkeletalMeshSocket(USkeletalMesh* Mesh, const FString& SocketName)
{
    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    if (!Mesh)
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), TEXT("SkeletalMesh is null."));
        return SerializeJsonObj(R);
    }
    USkeletalMeshSocket* Socket = Mesh->FindSocket(FName(*SocketName));
    if (!Socket)
    {
        R->SetBoolField(TEXT("success"), false);
        R->SetStringField(TEXT("message"), FString::Printf(TEXT("Socket '%s' not found."), *SocketName));
        return SerializeJsonObj(R);
    }

    Mesh->Modify();
    TArray<TObjectPtr<USkeletalMeshSocket>>& Sockets = Mesh->GetMeshOnlySocketList();
    Sockets.Remove(Socket);
    Mesh->MarkPackageDirty();

    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("removed"), SocketName);
    R->SetStringField(TEXT("message"), FString::Printf(TEXT("Removed socket '%s'."), *SocketName));
    return SerializeJsonObj(R);
}

// ─── Response transport (python_call) ─────────────────────────────────────────

static TOptional<FString> GMCPythonSubmittedResult;

void UMCPythonHelper::SubmitResult(const FString& ResultJson)
{
    GMCPythonSubmittedResult = ResultJson;
}

bool UMCPythonHelper::ConsumeSubmittedResult(FString& OutResult)
{
    if (GMCPythonSubmittedResult.IsSet())
    {
        OutResult = MoveTemp(GMCPythonSubmittedResult.GetValue());
        GMCPythonSubmittedResult.Reset();
        return true;
    }
    return false;
}

void UMCPythonHelper::ClearSubmittedResult()
{
    GMCPythonSubmittedResult.Reset();
}

// ─── Editor viewport projection ──────────────────────────────────────────────

static FLevelEditorViewportClient* GetActiveLevelViewportClient()
{
    if (GCurrentLevelEditingViewportClient && GCurrentLevelEditingViewportClient->Viewport)
        return GCurrentLevelEditingViewportClient;
    if (GEditor)
    {
        for (FLevelEditorViewportClient* VC : GEditor->GetLevelViewportClients())
            if (VC && VC->Viewport && VC->Viewport->GetSizeXY().X > 0)
                return VC;
    }
    return nullptr;
}

static TArray<TSharedPtr<FJsonValue>> VectorToJsonArray(const FVector& V)
{
    TArray<TSharedPtr<FJsonValue>> A;
    A.Add(MakeShareable(new FJsonValueNumber(V.X)));
    A.Add(MakeShareable(new FJsonValueNumber(V.Y)));
    A.Add(MakeShareable(new FJsonValueNumber(V.Z)));
    return A;
}

FString UMCPythonHelper::WorldToScreen(FVector WorldLocation)
{
    FLevelEditorViewportClient* VC = GetActiveLevelViewportClient();
    if (!VC)
        return MakeJsonError(TEXT("No active level viewport."));

    FSceneViewFamilyContext ViewFamily(FSceneViewFamily::ConstructionValues(
        VC->Viewport, VC->GetScene(), VC->EngineShowFlags).SetRealtimeUpdate(VC->IsRealtime()));
    FSceneView* View = VC->CalcSceneView(&ViewFamily);
    if (!View)
        return MakeJsonError(TEXT("Could not calculate the scene view."));

    FVector2D Pixel;
    const bool bInFront = View->WorldToPixel(WorldLocation, Pixel);
    const FIntPoint Size = VC->Viewport->GetSizeXY();
    const bool bOnScreen = bInFront && Pixel.X >= 0 && Pixel.Y >= 0 && Pixel.X <= Size.X && Pixel.Y <= Size.Y;

    TSharedPtr<FJsonObject> R = MakeShareable(new FJsonObject());
    R->SetBoolField(TEXT("success"), true);
    R->SetNumberField(TEXT("x"), Pixel.X);
    R->SetNumberField(TEXT("y"), Pixel.Y);
    R->SetBoolField(TEXT("visible"), bInFront);      // in front of the camera (not clipped)
    R->SetBoolField(TEXT("on_screen"), bOnScreen);   // also within the viewport rect
    R->SetNumberField(TEXT("viewport_width"), Size.X);
    R->SetNumberField(TEXT("viewport_height"), Size.Y);
    return SerializeJsonObj(R);
}

FString UMCPythonHelper::ScreenToWorld(float ScreenX, float ScreenY, float Distance)
{
    FLevelEditorViewportClient* VC = GetActiveLevelViewportClient();
    if (!VC)
        return MakeJsonError(TEXT("No active level viewport."));

    FSceneViewFamilyContext ViewFamily(FSceneViewFamily::ConstructionValues(
        VC->Viewport, VC->GetScene(), VC->EngineShowFlags).SetRealtimeUpdate(VC->IsRealtime()));
    FSceneView* View = VC->CalcSceneView(&ViewFamily);
    if (!View)
        return MakeJsonError(TEXT("Could not calculate the scene view."));

    FVector Origin, Direction;
    View->DeprojectFVector2D(FVector2D(ScreenX, ScreenY), Origin, Direction);
    const FVector Location = Origin + Direction * Distance;

    TSharedPtr<FJsonObject> R = MakeShareable(new FJsonObject());
    R->SetBoolField(TEXT("success"), true);
    R->SetArrayField(TEXT("location"), VectorToJsonArray(Location));
    R->SetArrayField(TEXT("origin"), VectorToJsonArray(Origin));
    R->SetArrayField(TEXT("direction"), VectorToJsonArray(Direction));
    R->SetNumberField(TEXT("distance"), Distance);
    return SerializeJsonObj(R);
}
