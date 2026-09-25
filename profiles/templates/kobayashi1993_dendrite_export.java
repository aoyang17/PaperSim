/** PaperSim export-only contract for Kobayashi 1993. */

import com.comsol.model.*;
import com.comsol.model.util.*;
import java.io.IOException;

/** Export every stored parametric solution from an existing solved MPH. */
public final class Kobayashi1993DendriteExport {
  public static void main(String[] args) throws IOException {
    Model model = ModelUtil.load("Kobayashi1993Dendrite", "iter001_solved.mph");

    model.result().numerical("gev1").set("data", "dset2");
    model.result().numerical("gev1").set("innerinput", "all");
    model.result().numerical("gev1").setResult();
    model.result().table("tblGlobal").save("iter001_global_all.csv");

    model.result().export("data1").set("data", "dset2");
    model.result().export("data1").set("innerinput", "interp");
    model.result().export("data1").set("t", new double[]{0.2, 0.8, 1.4});
    model.result().export("data1").set("filename", "iter001_fields_all.csv");
    model.result().export("data1").run();
  }
}
