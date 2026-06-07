// JavaScript source code
$(function () {
    $(".collapse-group").each(function (index) {
        var group = $(this);
        var sidebar = group.find(".sidebar").first();
        var mainContainer = group.find("main .container-fluid").first();

        if (!sidebar.length || !mainContainer.length || mainContainer.find(".mrf-mobile-tools").length) {
            return;
        }

        sidebar.attr("aria-label", "Page contents");

        var navList = sidebar.children("ul.nav").first().clone();
        if (!navList.length) {
            return;
        }

        var collapseId = "mrf-mobile-contents-" + index;
        var mobileTools = $('<div class="d-sm-none mrf-mobile-tools"></div>');
        var toggleButton = $(
            '<button class="btn btn-outline-secondary btn-block" type="button" data-toggle="collapse" aria-expanded="false">Contents</button>'
        );
        toggleButton.attr("data-target", "#" + collapseId);
        toggleButton.attr("aria-controls", collapseId);
        mobileTools.append(toggleButton);

        var mobileNavCollapse = $('<div class="collapse mrf-mobile-nav-collapse"></div>');
        mobileNavCollapse.attr("id", collapseId);
        var mobileNav = $('<nav class="mrf-mobile-nav bg-light" aria-label="Mobile page contents"></nav>');
        mobileNav.append(navList);
        mobileNavCollapse.append(mobileNav);
        mobileTools.append(mobileNavCollapse);

        mainContainer.prepend(mobileTools);
    });

    $(".open-button").on("click", function () {
        $(this).closest(".collapse-group").find(".collapse").not(".mrf-mobile-nav-collapse").collapse("show");
    });

    $(".close-button").on("click", function () {
        $(this).closest(".collapse-group").find(".collapse").not(".mrf-mobile-nav-collapse").collapse("hide");
    });

    $(document).on("click", ".mrf-mobile-nav a", function () {
        $(this).closest(".mrf-mobile-nav-collapse").collapse("hide");
    });
});
